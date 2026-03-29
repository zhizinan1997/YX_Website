import sys

with open('admin/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

css_start = -1
css_end = -1
html_start = -1
html_end = -1

for i, line in enumerate(lines):
    if '/* --- Login Page --- */' in line:
        css_start = i
    elif '/* --- Dashboard --- */' in line:
        css_end = i
    elif '<!-- LOGIN PAGE -->' in line:
        html_start = i
    elif 'id="loginFailModal"' in line:
        html_end = i

print(f"css_start={css_start}, css_end={css_end}, html_start={html_start}, html_end={html_end}")

if css_start != -1 and css_end != -1 and html_start != -1 and html_end != -1:
    new_css = """        /* --- Login Page Redesign --- */
        .login-page {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background: #0f172a;
            position: relative;
            overflow: hidden;
            font-family: 'Inter', sans-serif;
            color: #f8fafc;
        }

        .animated-bg {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: radial-gradient(circle at 15% 50%, rgba(56, 189, 248, 0.15), transparent 40%),
                        radial-gradient(circle at 85% 30%, rgba(99, 102, 241, 0.15), transparent 40%),
                        radial-gradient(circle at 50% 80%, rgba(20, 184, 166, 0.1), transparent 40%);
            z-index: 1;
            animation: pulse-bg 15s infinite alternate ease-in-out;
            pointer-events: none;
        }
        
        @keyframes pulse-bg {
            0% { transform: scale(1); }
            100% { transform: scale(1.1); }
        }

        .glass-sphere {
            position: absolute;
            border-radius: 50%;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0));
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
            z-index: 2;
            animation: float 8s ease-in-out infinite alternate;
            pointer-events: none;
        }

        .sphere-1 {
            width: 320px; height: 320px;
            top: -120px; left: -100px;
            background: linear-gradient(135deg, rgba(56, 189, 248, 0.15), rgba(30, 58, 138, 0.05));
            animation-delay: 0s;
        }

        .sphere-2 {
            width: 240px; height: 240px;
            bottom: -60px; right: -80px;
            background: linear-gradient(135deg, rgba(167, 139, 250, 0.15), rgba(76, 29, 149, 0.05));
            animation-delay: -3s;
        }

        @keyframes float {
            0% { transform: translateY(0px) rotate(0deg); }
            100% { transform: translateY(40px) rotate(10deg); }
        }

        .login-box-wrapper {
            position: relative;
            z-index: 10;
            width: 100%;
            max-width: 440px;
            padding: 30px;
        }

        .login-box {
            background: rgba(15, 23, 42, 0.65);
            backdrop-filter: blur(24px) saturate(180%);
            -webkit-backdrop-filter: blur(24px) saturate(180%);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 24px;
            padding: 40px 36px;
            box-shadow: 0 24px 64px rgba(0, 0, 0, 0.4), inset 0 1px 1px rgba(255, 255, 255, 0.1);
            color: #f8fafc;
            text-align: center;
        }

        .login-logo {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            background: linear-gradient(135deg, #38bdf8 0%, #a855f7 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 10px 30px rgba(56, 189, 248, 0.2);
        }

        .login-logo i {
            -webkit-text-fill-color: initial;
            color: #38bdf8;
            background: none;
        }

        .login-subtitle {
            color: #94a3b8;
            font-size: 14px;
            margin-bottom: 32px;
            font-weight: 300;
        }

        .login-page .form-group {
            margin-bottom: 24px;
            text-align: left;
            position: relative;
        }

        .login-page .form-group label {
            display: block;
            margin-bottom: 8px;
            font-size: 13px;
            font-weight: 500;
            color: #cbd5e1;
            letter-spacing: 0.5px;
        }

        .login-page .input-icon {
            position: absolute;
            left: 16px;
            top: 38px;
            color: #64748b;
            font-size: 16px;
            transition: color 0.3s;
        }

        .login-page .form-control {
            width: 100%;
            padding: 14px 16px 14px 44px;
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            font-size: 15px;
            color: #f8fafc;
            transition: all 0.3s ease;
            box-sizing: border-box;
        }

        .login-page .form-control::placeholder {
            color: #475569;
        }

        .login-page .form-control:focus {
            background: rgba(30, 41, 59, 0.9);
            border-color: #38bdf8;
            box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.15);
            outline: none;
        }

        .login-page .form-control:focus + .input-icon {
            color: #38bdf8;
        }

        .login-page .btn-primary {
            width: 100%;
            padding: 14px;
            border-radius: 12px;
            border: none;
            font-size: 15px;
            font-weight: 600;
            color: #fff;
            background: linear-gradient(135deg, #0ea5e9, #6366f1);
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            box-shadow: 0 8px 20px rgba(14, 165, 233, 0.3);
            margin-top: 10px;
        }

        .login-page .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 28px rgba(99, 102, 241, 0.4);
            filter: brightness(1.1);
        }

        .login-security-tip {
            margin-top: 24px;
            padding: 12px;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 10px;
            font-size: 12px;
            color: #34d399;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }

        .login-foot-link {
            margin-top: 24px;
            font-size: 13px;
        }

        .login-foot-link a {
            color: #64748b;
            text-decoration: none;
            transition: color 0.3s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .login-foot-link a:hover {
            color: #38bdf8;
        }

        .login-page #loginTurnstileWidget {
            display: flex;
            justify-content: center;
            align-items: center;
            background: rgba(30,41,59,0.5);
            border-radius: 12px;
            padding: 10px;
        }
        
        .login-page .error-message {
            margin-top: 12px;
            padding: 10px 14px;
            border-radius: 10px;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            color: #fca5a5;
            font-size: 13px;
            text-align: left;
            display: none;
        }
        
        .login-page .error-message:not(:empty) {
            display: block;
        }

        .login-fail-modal {
            position: fixed;
            inset: 0;
            z-index: 3600;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            background: rgba(2, 21, 44, 0.6);
            backdrop-filter: blur(4px);
        }

        .login-fail-modal[hidden] {
            display: none !important;
        }

        .login-fail-dialog {
            width: min(420px, 96vw);
            background: #fff;
            border-radius: 16px;
            box-shadow: 0 24px 64px rgba(0, 0, 0, 0.4);
            border: 1px solid #e5e7eb;
            padding: 24px;
        }

        .login-fail-head {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 16px;
        }

        .login-fail-icon {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #fee2e2;
            color: #b91c1c;
            font-size: 18px;
            flex-shrink: 0;
        }

        .login-fail-head h3 {
            font-size: 18px;
            color: #0f172a;
            margin: 0;
            font-weight: 700;
        }

        .login-fail-reason {
            color: #475569;
            line-height: 1.6;
            font-size: 14px;
            margin: 0 0 24px;
            word-break: break-word;
        }

        .login-fail-actions {
            display: flex;
            justify-content: flex-end;
        }

        .login-fail-close-btn {
            border: none;
            border-radius: 10px;
            padding: 10px 20px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            color: #fff;
            background: linear-gradient(135deg, #0f172a, #1e293b);
            transition: all 0.2s;
        }

        .login-fail-close-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.3);
        }

        @media (max-width: 640px) {
            .login-box {
                padding: 30px 24px;
                border-radius: 20px;
            }
            .sphere-1, .sphere-2 {
                display: none;
            }
        }
\n"""

    new_html = """    <!-- LOGIN PAGE -->
    <div id="loginPage" class="login-page">
        <div class="animated-bg"></div>
        <div class="glass-sphere sphere-1"></div>
        <div class="glass-sphere sphere-2"></div>
        <div class="login-box-wrapper">
            <div class="login-box">
                <div class="login-logo">
                    <i class="fas fa-shield-alt"></i> 元芯传感后台
                </div>
                <p class="login-subtitle">仅授权管理员可访问，请使用账号密码登录。</p>
                <form id="loginForm">
                    <div class="form-group">
                        <label>用户名</label>
                        <input type="text" id="username" class="form-control" placeholder="请输入用户名" required>
                        <i class="fas fa-user input-icon"></i>
                    </div>
                    <div class="form-group">
                        <label>密码</label>
                        <input type="password" id="password" class="form-control" placeholder="请输入密码" required>
                        <i class="fas fa-lock input-icon"></i>
                    </div>
                    <div id="loginTurnstileWrap" class="form-group" style="display:none;">
                        <label>人机验证</label>
                        <div id="loginTurnstileWidget"></div>
                        <div id="loginTurnstileError" class="error-message"></div>
                    </div>
                    <button type="submit" id="loginSubmitBtn" class="btn-primary">
                        <span>登 录</span> <i class="fas fa-arrow-right"></i>
                    </button>
                    <div id="loginError" class="error-message"></div>
                </form>
                <div class="login-security-tip">
                    <i class="fas fa-shield-virus"></i>
                    <span>安全防护中 · 12小时内失败3次将封禁IP</span>
                </div>
                <div class="login-foot-link">
                    <a href="/"><i class="fas fa-arrow-left"></i> 返回网站首页</a>
                </div>
            </div>
        </div>
    </div>\n
"""

    final_lines = lines[:css_start] + [new_css] + lines[css_end:html_start] + [new_html] + lines[html_end:]
    
    with open('admin/index.html', 'w', encoding='utf-8') as f:
        f.writelines(final_lines)
    print("Successfully applied redesigned UI.")
else:
    print("Failed to find boundaries in the file.")
