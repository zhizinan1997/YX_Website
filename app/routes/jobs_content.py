"""Jobs/careers helpers and routes."""

from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path

from flask import jsonify, request

_DEPS = {}


def configure_jobs_content(*, jobs_file, pages_dir, sanitize_news_html_fragment):
    """Configure shared dependencies for jobs helpers/routes."""
    _DEPS.clear()
    _DEPS.update({
        'jobs_file': Path(jobs_file),
        'pages_dir': Path(pages_dir),
        'sanitize_news_html_fragment': sanitize_news_html_fragment,
    })


def _dep(name):
    value = _DEPS.get(name)
    if value is None and name not in _DEPS:
        raise RuntimeError(f'Jobs content dependency not configured: {name}')
    return value


def parse_jobs_from_html(html_text):
    """Parse jobs list from legacy job.aspx.html."""
    try:
        match = re.search(r'<ul class="jobs_list">(.*?)</ul>', html_text, re.S)
        if not match:
            return []
        block = match.group(1)
        items = re.findall(r'<li>(.*?)</li>', block, re.S)

        def clean(text):
            text = re.sub(r'<[^>]+>', '', text)
            text = text.replace('&nbsp;', ' ').replace('\xa0', ' ')
            return ' '.join(text.split()).strip()

        def after(label, text):
            if label in text:
                text = text.split(label, 1)[1]
            return text.replace(':', '').replace('：', '').strip()

        jobs = []
        for idx, li in enumerate(items, 1):
            show = re.search(r'<div class="jobs_show">(.*?)</div>', li, re.S)
            spans = re.findall(r'<span[^>]*>(.*?)</span>', show.group(1) if show else '', re.S)
            spans = [clean(span) for span in spans]
            title = after('职位名称', spans[0]) if len(spans) > 0 else ''
            department = after('招聘部门', spans[1]) if len(spans) > 1 else ''
            location = after('工作地点', spans[2]) if len(spans) > 2 else ''
            date = after('发布日期', spans[3]) if len(spans) > 3 else ''
            desc_match = re.search(r'<dl class="gwzz">(.*?)</dl>', li, re.S)
            content_html = desc_match.group(1).strip() if desc_match else ''
            jobs.append({
                'id': f'job_{idx}',
                'title': title,
                'department': department,
                'location': location,
                'date': date,
                'content_html': content_html,
                'visible': True,
            })
        return jobs
    except Exception:
        return []


def clean_job_text(value: str) -> str:
    """Normalize legacy whitespace/HTML entities in job fields."""
    if value is None:
        return ''
    text = str(value)
    text = text.replace('\u00a0', ' ')
    text = re.sub(r'&nbsp;?', ' ', text, flags=re.IGNORECASE)
    text = html.unescape(text)
    text = text.replace('\u00a0', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def normalize_job_date(value: str) -> str:
    """Normalize date to YYYY-MM-DD for input[type=date] compatibility."""
    text = clean_job_text(value)
    if not text:
        return ''

    match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
    if not match:
        match = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})', text)
    if match:
        year, month, day = match.groups()
        return f'{int(year):04d}-{int(month):02d}-{int(day):02d}'
    return text


def normalize_job_record(item):
    """Sanitize one job object from storage/user input."""
    if not isinstance(item, dict):
        return None
    return {
        'id': clean_job_text(item.get('id') or ''),
        'title': clean_job_text(item.get('title') or ''),
        'department': clean_job_text(item.get('department') or ''),
        'location': clean_job_text(item.get('location') or ''),
        'date': normalize_job_date(item.get('date') or ''),
        'content_html': _dep('sanitize_news_html_fragment')(item.get('content_html') or ''),
        'visible': bool(item.get('visible', True)),
    }


def load_jobs_data():
    jobs_file = _dep('jobs_file')
    if jobs_file.exists():
        try:
            data = json.loads(jobs_file.read_text(encoding='utf-8'))
            if isinstance(data, dict) and isinstance(data.get('jobs', []), list):
                normalized_jobs = []
                changed = False
                for raw in data.get('jobs', []):
                    normalized = normalize_job_record(raw)
                    if not normalized:
                        changed = True
                        continue
                    normalized_jobs.append(normalized)
                    if normalized != raw:
                        changed = True
                normalized_data = {'jobs': normalized_jobs}
                if changed:
                    save_jobs_data(normalized_data)
                return normalized_data
        except Exception:
            pass

    legacy_path = _dep('pages_dir') / 'careers' / 'job.aspx.html'
    jobs = []
    if legacy_path.exists():
        jobs = parse_jobs_from_html(legacy_path.read_text(encoding='utf-8', errors='ignore'))
    data = {'jobs': jobs}
    jobs_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data


def save_jobs_data(data):
    jobs = []
    for raw in (data or {}).get('jobs', []):
        normalized = normalize_job_record(raw)
        if normalized:
            jobs.append(normalized)
    _dep('jobs_file').write_text(json.dumps({'jobs': jobs}, ensure_ascii=False, indent=2), encoding='utf-8')


def register_jobs_content_routes(
    app,
    *,
    login_required,
    jobs_file,
    pages_dir,
    sanitize_news_html_fragment,
):
    """Register jobs/careers routes."""
    configure_jobs_content(
        jobs_file=jobs_file,
        pages_dir=pages_dir,
        sanitize_news_html_fragment=sanitize_news_html_fragment,
    )

    @app.route('/api/jobs')
    @login_required
    def get_jobs_admin():
        data = load_jobs_data()
        return jsonify({'items': data.get('jobs', [])})

    @app.route('/api/jobs', methods=['POST'])
    @login_required
    def save_job_admin():
        data = request.json or {}
        title = clean_job_text(data.get('title') or '')
        department = clean_job_text(data.get('department') or '')
        location = clean_job_text(data.get('location') or '')
        date = normalize_job_date(data.get('date') or '')
        content_html = _dep('sanitize_news_html_fragment')(data.get('content_html') or '')
        visible = bool(data.get('visible', True))
        job_id = clean_job_text(data.get('id') or '')

        if not title or not department or not location or not date:
            return jsonify({'success': False, 'message': '请填写完整的职位信息'}), 400

        jobs_data = load_jobs_data()
        jobs = jobs_data.get('jobs', [])

        if job_id:
            updated = False
            for job in jobs:
                if job.get('id') == job_id:
                    job.update({
                        'title': title,
                        'department': department,
                        'location': location,
                        'date': date,
                        'content_html': content_html,
                        'visible': visible,
                    })
                    updated = True
                    break
            if not updated:
                jobs.append({
                    'id': job_id,
                    'title': title,
                    'department': department,
                    'location': location,
                    'date': date,
                    'content_html': content_html,
                    'visible': visible,
                })
        else:
            new_id = f'job_{int(time.time() * 1000)}'
            jobs.append({
                'id': new_id,
                'title': title,
                'department': department,
                'location': location,
                'date': date,
                'content_html': content_html,
                'visible': visible,
            })

        jobs_data['jobs'] = jobs
        save_jobs_data(jobs_data)
        return jsonify({'success': True, 'items': jobs})

    @app.route('/api/jobs/<job_id>', methods=['DELETE'])
    @login_required
    def delete_job_admin(job_id):
        jobs_data = load_jobs_data()
        jobs = [job for job in jobs_data.get('jobs', []) if job.get('id') != job_id]
        jobs_data['jobs'] = jobs
        save_jobs_data(jobs_data)
        return jsonify({'success': True})

    @app.route('/api/jobs/<job_id>/toggle', methods=['POST'])
    @login_required
    def toggle_job_admin(job_id):
        jobs_data = load_jobs_data()
        for job in jobs_data.get('jobs', []):
            if job.get('id') == job_id:
                job['visible'] = not bool(job.get('visible', True))
                save_jobs_data(jobs_data)
                return jsonify({'success': True, 'visible': job['visible']})
        return jsonify({'success': False, 'message': '未找到职位'}), 404

    @app.route('/api/jobs/public')
    def get_jobs_public():
        data = load_jobs_data()
        items = [job for job in data.get('jobs', []) if job.get('visible', True)]
        return jsonify({'items': items})
