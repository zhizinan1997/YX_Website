"""AI chatbot, knowledge-base, and product-AI config helpers/routes."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path

from flask import Response, jsonify, request, stream_with_context

_DEPS = {}
_knowledge_cache = {
    'content': '',
    'last_updated': 0,
    'files': [],
}
_knowledge_lock = threading.Lock()

CHATBOT_SYSTEM_PROMPT = '''你是元芯传感的智能客服助手。你的职责是回答用户关于公司产品、技术和服务的问题。

公司信息：
- 公司名称：湖南元芯传感科技有限责任公司
- 主要业务：先进生物与化学传感技术解决方案
- 核心技术：碳基电子传感技术
- 主要产品：氢气传感器、生物传感器、气体检测模组

请用专业、友好的语气回答问题。如果遇到不确定的问题，请引导用户联系我们的销售团队。'''

PRODUCT_AI_SYSTEM_PROMPT = '''你是“元芯传感产品页编程助手”，负责根据后台给定的产品资料生成可发布的页面内容。

你在“产品页编程 AI”场景下的硬性规则：
1) 你的输出目标是完整 HTML 页面代码。
2) 请直接开始写代码，代码写完后不要添加任何其他内容。
3) 禁止输出解释、注释说明、Markdown代码块（```）。
4) 输出尽量完整，包含 <!DOCTYPE html>、<html>、<head>、<body>。
5) 必须参考提供的模板结构与样式，不要无故删除关键布局和资源引用。
6) 文案专业、克制、可发布；禁止编造认证/资质/客户背书。
7) 图片或链接未知时可使用占位路径 /assets/images/logo.png 或保守留空。'''


def configure_ai_chatbot(
    *,
    get_config,
    update_config,
    require_super_admin_api,
    sanitize_public_link_url,
    validate_uploaded_pdf,
    knowledge_dir,
    pdf_support,
    pypdf2_module,
    requests_support,
    requests_module,
    httpx_support,
    httpx_module,
):
    """Configure shared dependencies for AI/chatbot helpers."""
    _DEPS.clear()
    _DEPS.update({
        'get_config': get_config,
        'update_config': update_config,
        'require_super_admin_api': require_super_admin_api,
        'sanitize_public_link_url': sanitize_public_link_url,
        'validate_uploaded_pdf': validate_uploaded_pdf,
        'knowledge_dir': Path(knowledge_dir),
        'pdf_support': bool(pdf_support),
        'pypdf2_module': pypdf2_module,
        'requests_support': bool(requests_support),
        'requests_module': requests_module,
        'httpx_support': bool(httpx_support),
        'httpx_module': httpx_module,
    })


def _dep(name):
    value = _DEPS.get(name)
    if value is None and name not in _DEPS:
        raise RuntimeError(f'AI chatbot dependency not configured: {name}')
    return value


def get_chatbot_system_prompt():
    return CHATBOT_SYSTEM_PROMPT


def get_product_page_ai_system_prompt():
    return PRODUCT_AI_SYSTEM_PROMPT


def get_chatbot_config():
    """Get chatbot configuration from shared site config."""
    config = _dep('get_config')()
    return {
        'api_key': config.get('chatbot_api_key', ''),
        'api_base': config.get('chatbot_api_base', 'https://api.openai.com/v1'),
        'model': config.get('chatbot_model', 'gpt-3.5-turbo'),
        'enabled': config.get('chatbot_enabled', True),
    }


def get_product_page_ai_config():
    """Get product-page coding AI configuration from shared site config."""
    config = _dep('get_config')()
    return {
        'enabled': config.get('product_ai_enabled', False),
        'api_key': config.get('product_ai_api_key', ''),
        'api_base': config.get('product_ai_api_base', 'https://api.openai.com/v1'),
        'model': config.get('product_ai_model', 'gpt-4o-mini'),
    }


def load_knowledge_base():
    """Load and cache knowledge base content from PDF files."""
    knowledge_dir = _dep('knowledge_dir')
    pdf_support = _dep('pdf_support')
    pypdf2_module = _dep('pypdf2_module')

    with _knowledge_lock:
        pdf_files = list(knowledge_dir.glob('*.pdf'))
        current_files = sorted([f.name for f in pdf_files])
        current_mtime = max([f.stat().st_mtime for f in pdf_files]) if pdf_files else 0

        if (
            _knowledge_cache['files'] == current_files
            and _knowledge_cache['last_updated'] >= current_mtime
            and _knowledge_cache['content']
        ):
            return _knowledge_cache['content']

        if not pdf_support or pypdf2_module is None:
            return ''

        knowledge_text = []
        for pdf_path in pdf_files:
            try:
                with open(pdf_path, 'rb') as fh:
                    reader = pypdf2_module.PdfReader(fh)
                    pdf_text = []
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            pdf_text.append(text)
                    if pdf_text:
                        knowledge_text.append(f"\n--- 来自文档: {pdf_path.name} ---\n")
                        knowledge_text.append('\n'.join(pdf_text))
            except Exception as exc:
                print(f'Error reading PDF {pdf_path}: {exc}')
                continue

        _knowledge_cache['content'] = '\n'.join(knowledge_text)
        _knowledge_cache['last_updated'] = current_mtime
        _knowledge_cache['files'] = current_files
        return _knowledge_cache['content']


def call_openai_api(messages, stream=False):
    """Call OpenAI-compatible API in sync or stream mode."""
    if stream:
        return call_openai_api_stream(messages)
    return call_openai_api_sync(messages)


def call_openai_api_sync(messages):
    """Call OpenAI-compatible API (non-stream)."""
    config = get_chatbot_config()
    if not config['api_key']:
        return None, 'AI客服未配置，请联系管理员'

    api_url = config['api_base'].rstrip('/') + '/chat/completions'
    headers = {
        'Authorization': f"Bearer {config['api_key']}",
        'Content-Type': 'application/json',
    }
    payload = {
        'model': config['model'],
        'messages': messages,
        'stream': False,
    }

    requests_support = _dep('requests_support')
    requests_module = _dep('requests_module')
    httpx_support = _dep('httpx_support')
    httpx_module = _dep('httpx_module')

    try:
        if requests_support and requests_module is not None:
            response = requests_module.post(api_url, json=payload, headers=headers, timeout=60)
            if response.status_code != 200:
                return None, f'API错误: {response.status_code}'
            result = response.json()
            if 'choices' in result and result['choices']:
                return result['choices'][0]['message']['content'], None
            return None, 'API返回格式错误'
        if httpx_support and httpx_module is not None:
            response = httpx_module.post(api_url, json=payload, headers=headers, timeout=60.0)
            if response.status_code != 200:
                return None, f'API错误: {response.status_code}'
            result = response.json()
            if 'choices' in result and result['choices']:
                return result['choices'][0]['message']['content'], None
            return None, 'API返回格式错误'
        return None, '缺少HTTP客户端库(requests或httpx)'
    except Exception as exc:
        print(f'OpenAI API error: {exc}')
        return None, f'API调用失败: {str(exc)}'


def call_openai_api_stream(messages):
    """Call OpenAI-compatible API (stream)."""
    config = get_chatbot_config()
    if not config['api_key']:
        return None, 'AI客服未配置，请联系管理员'

    api_url = config['api_base'].rstrip('/') + '/chat/completions'
    headers = {
        'Authorization': f"Bearer {config['api_key']}",
        'Content-Type': 'application/json',
    }
    payload = {
        'model': config['model'],
        'messages': messages,
        'stream': True,
    }

    requests_support = _dep('requests_support')
    requests_module = _dep('requests_module')
    httpx_support = _dep('httpx_support')
    httpx_module = _dep('httpx_module')

    if httpx_support and httpx_module is not None:
        def gen_httpx():
            try:
                with httpx_module.Client(timeout=60.0) as client:
                    with client.stream('POST', api_url, json=payload, headers=headers) as response:
                        if response.status_code != 200:
                            yield None, f'API错误: {response.status_code}'
                            return
                        for line in response.iter_lines():
                            if line.startswith('data: '):
                                data = line[6:]
                                if data == '[DONE]':
                                    break
                                try:
                                    chunk = json.loads(data)
                                    if 'choices' in chunk and chunk['choices']:
                                        delta = chunk['choices'][0].get('delta', {})
                                        content = delta.get('content', '')
                                        if content:
                                            yield content, None
                                except json.JSONDecodeError:
                                    continue
            except Exception as exc:
                yield None, f'API调用失败: {str(exc)}'
        return gen_httpx()

    if requests_support and requests_module is not None:
        def gen_requests():
            try:
                response = requests_module.post(api_url, json=payload, headers=headers, stream=True, timeout=60)
                if response.status_code != 200:
                    yield None, f'API错误: {response.status_code}'
                    return
                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: '):
                            data = line[6:]
                            if data == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data)
                                if 'choices' in chunk and chunk['choices']:
                                    delta = chunk['choices'][0].get('delta', {})
                                    content = delta.get('content', '')
                                    if content:
                                        yield content, None
                            except json.JSONDecodeError:
                                continue
            except Exception as exc:
                yield None, f'API调用失败: {str(exc)}'
        return gen_requests()

    return None, '缺少HTTP客户端库(requests或httpx)'


def register_ai_chatbot_routes(
    app,
    *,
    login_required,
    get_config,
    update_config,
    require_super_admin_api,
    sanitize_public_link_url,
    validate_uploaded_pdf,
    knowledge_dir,
    pdf_support,
    pypdf2_module,
    requests_support,
    requests_module,
    httpx_support,
    httpx_module,
):
    """Register chatbot/knowledge/config routes and configure shared helpers."""
    configure_ai_chatbot(
        get_config=get_config,
        update_config=update_config,
        require_super_admin_api=require_super_admin_api,
        sanitize_public_link_url=sanitize_public_link_url,
        validate_uploaded_pdf=validate_uploaded_pdf,
        knowledge_dir=knowledge_dir,
        pdf_support=pdf_support,
        pypdf2_module=pypdf2_module,
        requests_support=requests_support,
        requests_module=requests_module,
        httpx_support=httpx_support,
        httpx_module=httpx_module,
    )

    @app.route('/api/chatbot/chat', methods=['POST'])
    def chatbot_chat():
        config = get_chatbot_config()
        if not config['enabled']:
            return jsonify({'success': False, 'message': '智能客服暂时不可用'}), 503

        data = request.json or {}
        user_message = str(data.get('message') or '').strip()
        history = data.get('history', [])
        if not user_message:
            return jsonify({'success': False, 'message': '请输入您的问题'}), 400

        knowledge = load_knowledge_base()
        system_prompt = get_chatbot_system_prompt()
        if knowledge:
            system_prompt += f"\n\n以下是公司知识库的相关内容，请参考这些信息回答用户问题：\n{knowledge[:8000]}"

        messages = [{'role': 'system', 'content': system_prompt}]
        for msg in history[-8:]:
            role = msg.get('role', 'user')
            if role == 'assistant':
                role = 'assistant'
            messages.append({'role': role, 'content': msg.get('content', '')})
        messages.append({'role': 'user', 'content': user_message})

        def build_local_fallback_reply(text):
            q = str(text or '').strip()
            q_l = q.lower()

            def has_any(*words):
                return any(w in q_l or w in q for w in words)

            if has_any('报价', '价格', '采购'):
                return '您可以通过在线留言提交需求，我们会安排技术与销售跟进：[在线留言](/pages/contact/feedback.html#feedbackForm)。'
            if has_any('联系', '电话', '留言'):
                return '您可以通过在线留言提交需求，我们会安排技术与销售跟进：[在线留言](/pages/contact/feedback.html#feedbackForm)。'
            if has_any('介绍', '公司', '元芯'):
                return '元芯传感专注于气体传感与检测技术，覆盖传感器、检测模组与行业应用方案。如果您告诉我应用场景，我可以继续给出更具体的产品建议。'
            if has_any('产品', '传感器', '氢气', '型号'):
                return '您可以先查看气体传感产品总览页，按场景筛选型号：[查看全部产品](/pages/gassensing/all-products.html)。'
            if has_any('方案', '行业', '应用', '解决'):
                return '行业方案可以从这里进入：[解决方案中心](/pages/solutions/solutions-index.html)。如果您告知工况（温湿度、量程、安装方式），我可以继续细化建议。'
            return '抱歉，智能对话服务当前连接不稳定。建议先在“在线留言”提交问题，我们会尽快人工回复：[在线留言](/pages/contact/feedback.html#feedbackForm)。'

        fallback_reply = build_local_fallback_reply(user_message)
        use_stream = httpx_support or (requests_support and config.get('use_stream', True))

        if use_stream:
            def generate():
                sent_any_content = False
                try:
                    stream = call_openai_api(messages, stream=True)
                    if isinstance(stream, tuple):
                        _, error = stream
                        app.logger.warning('chatbot stream init failed: %s', error)
                        sync_response, sync_error = call_openai_api(messages, stream=False)
                        if not sync_error and sync_response:
                            yield f"data: {json.dumps({'content': sync_response}, ensure_ascii=False)}\n\n"
                            yield 'data: [DONE]\n\n'
                            return
                        app.logger.warning('chatbot sync fallback after stream init failed: %s', sync_error)
                        yield f"data: {json.dumps({'content': fallback_reply}, ensure_ascii=False)}\n\n"
                        yield 'data: [DONE]\n\n'
                        return
                    for chunk, err in stream:
                        if err:
                            app.logger.warning('chatbot stream chunk failed: %s', err)
                            if not sent_any_content:
                                sync_response, sync_error = call_openai_api(messages, stream=False)
                                if not sync_error and sync_response:
                                    yield f"data: {json.dumps({'content': sync_response}, ensure_ascii=False)}\n\n"
                                    yield 'data: [DONE]\n\n'
                                    return
                                app.logger.warning('chatbot sync fallback after stream chunk failed: %s', sync_error)
                            fallback_content = '\n\n' + fallback_reply if sent_any_content else fallback_reply
                            yield f"data: {json.dumps({'content': fallback_content}, ensure_ascii=False)}\n\n"
                            yield 'data: [DONE]\n\n'
                            return
                        sent_any_content = True
                        yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                    if not sent_any_content:
                        yield f"data: {json.dumps({'content': fallback_reply}, ensure_ascii=False)}\n\n"
                    yield 'data: [DONE]\n\n'
                except Exception as exc:
                    app.logger.exception('chatbot stream exception: %s', exc)
                    sync_response, sync_error = call_openai_api(messages, stream=False)
                    if not sync_error and sync_response:
                        yield f"data: {json.dumps({'content': sync_response}, ensure_ascii=False)}\n\n"
                        yield 'data: [DONE]\n\n'
                        return
                    app.logger.warning('chatbot sync fallback after stream exception failed: %s', sync_error)
                    yield f"data: {json.dumps({'content': fallback_reply}, ensure_ascii=False)}\n\n"
                    yield 'data: [DONE]\n\n'

            return Response(
                stream_with_context(generate()),
                mimetype='text/event-stream',
                headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
            )

        response, error = call_openai_api(messages, stream=False)
        if error:
            app.logger.warning('chatbot non-stream failed: %s', error)
            return jsonify({'success': True, 'response': fallback_reply})
        return jsonify({'success': True, 'response': response})

    @app.route('/api/chatbot/knowledge', methods=['GET'])
    @login_required
    def list_knowledge_files():
        files = []
        for pdf_path in sorted(_dep('knowledge_dir').glob('*.pdf')):
            stat = pdf_path.stat()
            files.append({
                'name': pdf_path.name,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        return jsonify({'files': files, 'pdf_support': _dep('pdf_support')})

    @app.route('/api/chatbot/knowledge/upload', methods=['POST'])
    @login_required
    def upload_knowledge_file():
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有上传文件'}), 400
        file = request.files['file']
        if not file.filename:
            return jsonify({'success': False, 'message': '文件名为空'}), 400
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'success': False, 'message': '只支持PDF文件'}), 400
        if not _dep('validate_uploaded_pdf')(file):
            return jsonify({'success': False, 'message': 'PDF 文件格式无效'}), 400

        filename = re.sub(r'[^\w\u4e00-\u9fff\-_.]', '_', file.filename)
        filepath = _dep('knowledge_dir') / filename
        try:
            file.save(str(filepath))
            with _knowledge_lock:
                _knowledge_cache['content'] = ''
                _knowledge_cache['last_updated'] = 0
            return jsonify({'success': True, 'message': f'文件 {filename} 上传成功', 'filename': filename})
        except Exception as exc:
            return jsonify({'success': False, 'message': f'上传失败: {str(exc)}'}), 500

    @app.route('/api/chatbot/knowledge/<filename>', methods=['DELETE'])
    @login_required
    def delete_knowledge_file(filename):
        filepath = _dep('knowledge_dir') / filename
        if not filepath.exists():
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        try:
            filepath.unlink()
            with _knowledge_lock:
                _knowledge_cache['content'] = ''
                _knowledge_cache['last_updated'] = 0
            return jsonify({'success': True, 'message': '删除成功'})
        except Exception as exc:
            return jsonify({'success': False, 'message': f'删除失败: {str(exc)}'}), 500

    @app.route('/api/chatbot/config', methods=['GET'])
    @login_required
    def get_chatbot_config_api():
        config = get_chatbot_config()
        if config['api_key']:
            config['api_key'] = config['api_key'][:8] + '...' + config['api_key'][-4:] if len(config['api_key']) > 12 else '***'
        return jsonify(config)

    @app.route('/api/chatbot/config', methods=['POST'])
    @login_required
    def update_chatbot_config():
        denied = _dep('require_super_admin_api')()
        if denied:
            return denied
        data = request.json or {}
        updates = {}
        if 'api_key' in data and data['api_key'] and not str(data['api_key']).startswith('***'):
            updates['chatbot_api_key'] = str(data['api_key']).strip()
        if 'api_base' in data:
            safe_api_base = _dep('sanitize_public_link_url')(data['api_base'], enforce_remote_public=True)
            if not safe_api_base:
                return jsonify({'success': False, 'message': 'API Base 必须是有效的公网 http/https 地址'}), 400
            updates['chatbot_api_base'] = safe_api_base
        if 'model' in data:
            updates['chatbot_model'] = data['model']
        if 'enabled' in data:
            updates['chatbot_enabled'] = bool(data['enabled'])
        if updates:
            _dep('update_config')(updates)
        return jsonify({'success': True, 'message': '配置已更新'})

    @app.route('/api/product-ai/config', methods=['GET'])
    @login_required
    def get_product_ai_config_api():
        config = get_product_page_ai_config()
        if config['api_key']:
            config['api_key'] = config['api_key'][:8] + '...' + config['api_key'][-4:] if len(config['api_key']) > 12 else '***'
        return jsonify(config)

    @app.route('/api/product-ai/config', methods=['POST'])
    @login_required
    def update_product_ai_config():
        denied = _dep('require_super_admin_api')()
        if denied:
            return denied
        data = request.json or {}
        updates = {}
        if 'api_key' in data and data['api_key'] and not str(data['api_key']).startswith('***'):
            updates['product_ai_api_key'] = str(data['api_key']).strip()
        if 'api_base' in data:
            safe_api_base = _dep('sanitize_public_link_url')(data['api_base'], enforce_remote_public=True)
            if not safe_api_base:
                return jsonify({'success': False, 'message': 'API Base 必须是有效的公网 http/https 地址'}), 400
            updates['product_ai_api_base'] = safe_api_base
        if 'model' in data:
            updates['product_ai_model'] = str(data['model']).strip()
        if 'enabled' in data:
            updates['product_ai_enabled'] = bool(data['enabled'])
        if updates:
            _dep('update_config')(updates)
        return jsonify({'success': True, 'message': '产品页编程AI配置已更新'})
