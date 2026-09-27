(function () {
    'use strict';

    const state = { enabled: false, items: [], stepUpValid: false, pendingAction: null };

    function b64urlToBytes(value) {
        const input = String(value || '').replace(/-/g, '+').replace(/_/g, '/');
        const padded = input + '='.repeat((4 - input.length % 4) % 4);
        const raw = atob(padded);
        return Uint8Array.from(raw, c => c.charCodeAt(0));
    }

    function bytesToB64url(value) {
        const bytes = value instanceof ArrayBuffer ? new Uint8Array(value) : new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
        let raw = '';
        bytes.forEach(byte => { raw += String.fromCharCode(byte); });
        return btoa(raw).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
    }

    function prepareOptions(options) {
        const copy = JSON.parse(JSON.stringify(options || {}));
        copy.challenge = b64urlToBytes(copy.challenge);
        if (copy.user && copy.user.id) copy.user.id = b64urlToBytes(copy.user.id);
        for (const key of ['allowCredentials', 'excludeCredentials']) {
            if (Array.isArray(copy[key])) copy[key] = copy[key].map(item => ({ ...item, id: b64urlToBytes(item.id) }));
        }
        return copy;
    }

    function serializeCredential(credential) {
        const response = credential.response || {};
        const payload = {
            id: credential.id,
            rawId: bytesToB64url(credential.rawId),
            type: credential.type,
            authenticatorAttachment: credential.authenticatorAttachment || null,
            clientExtensionResults: credential.getClientExtensionResults ? credential.getClientExtensionResults() : {},
            response: {
                clientDataJSON: bytesToB64url(response.clientDataJSON)
            }
        };
        if (response.attestationObject) payload.response.attestationObject = bytesToB64url(response.attestationObject);
        if (response.authenticatorData) payload.response.authenticatorData = bytesToB64url(response.authenticatorData);
        if (response.signature) payload.response.signature = bytesToB64url(response.signature);
        if (response.userHandle) payload.response.userHandle = bytesToB64url(response.userHandle);
        if (typeof response.getTransports === 'function') payload.response.transports = response.getTransports();
        return payload;
    }

    async function jsonFetch(url, options) {
        const res = await fetch(url, options);
        let data = {};
        try { data = await res.json(); } catch (_) { }
        if (!res.ok || data.success === false) {
            const error = new Error(data.message || `请求失败（HTTP ${res.status}）`);
            error.status = res.status;
            error.data = data;
            throw error;
        }
        return data;
    }

    function setMessage(id, message, isError) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = message || '';
        el.style.color = isError ? '#b91c1c' : '#15803d';
    }

    function isUserCancellation(error) {
        return error && ['NotAllowedError', 'AbortError'].includes(error.name);
    }

    async function runPasskeyLogin() {
        const btn = document.getElementById('passkeyLoginBtn');
        if (btn) btn.disabled = true;
        setMessage('passkeyLoginMsg', '正在准备安全验证…', false);
        try {
            if (typeof window.runIpPreflight === 'function') {
                const preflight = await window.runIpPreflight();
                if (!preflight.allowed) return;
                await new Promise(resolve => setTimeout(resolve, 500));
                if (typeof window.closeIpPreflightModal === 'function') window.closeIpPreflightModal();
            }
            const start = await jsonFetch('/admin/passkey/login/options', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
            });
            const credential = await navigator.credentials.get({ publicKey: prepareOptions(start.options) });
            const result = await jsonFetch('/admin/passkey/login/verify', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    request_id: start.request_id,
                    credential: serializeCredential(credential),
                    remember_me: typeof window.getRememberMeFlag === 'function' ? window.getRememberMeFlag() : false
                })
            });
            setMessage('passkeyLoginMsg', '验证成功，正在进入后台…', false);
            if (typeof window.showLastLoginToast === 'function') {
                window.showLastLoginToast('Passkey', result.last_login_at, result.last_login_ip, result.current_login_at, result.current_login_ip);
            }
            if (typeof window.checkLoginStatus === 'function') await window.checkLoginStatus();
        } catch (error) {
            setMessage('passkeyLoginMsg', isUserCancellation(error) ? '已取消 Passkey 验证。' : (error.message || 'Passkey 登录失败。'), !isUserCancellation(error));
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async function loadPublicConfig() {
        const wrap = document.getElementById('passkeyLoginWrap');
        const card = document.getElementById('passkeySecurityCard');
        try {
            const data = await jsonFetch('/api/admin/passkey/public-config', { cache: 'no-store' });
            state.enabled = data.enabled === true && !!window.PublicKeyCredential && !!navigator.credentials;
        } catch (_) {
            state.enabled = false;
        }
        if (wrap) wrap.hidden = !state.enabled;
        if (card) card.hidden = !state.enabled;
    }

    function formatTime(value) {
        if (!value) return '从未使用';
        try { return new Date(value).toLocaleString('zh-CN', { hour12: false }); } catch (_) { return value; }
    }

    function renderDevices() {
        const list = document.getElementById('passkeyDeviceList');
        const status = document.getElementById('passkeySecurityStatus');
        if (status) status.textContent = state.items.length
            ? `已绑定 ${state.items.length} 个 Passkey，建议至少保留两个可用设备。`
            : '尚未绑定 Passkey。添加后可在登录页使用设备验证快速登录。';
        if (!list) return;
        if (!state.items.length) {
            list.innerHTML = '<div class="no-data">暂无 Passkey 登录设备</div>';
            return;
        }
        list.innerHTML = state.items.map(item => `
            <div class="passkey-device-item">
                <div class="passkey-device-meta">
                    <strong><i class="fas fa-fingerprint"></i> ${escapeText(item.device_name)}</strong>
                    <small>添加：${escapeText(formatTime(item.created_at))} · 最近使用：${escapeText(formatTime(item.last_used_at))}<br>${item.backup_eligible ? '可能通过密码管理器同步' : '设备或安全密钥凭据'} · ${escapeText(item.credential_fingerprint || '')}</small>
                </div>
                <div class="passkey-device-actions">
                    <button type="button" class="btn-sm" data-passkey-rename="${escapeText(item.credential_id)}">重命名</button>
                    <button type="button" class="btn-sm btn-danger" data-passkey-remove="${escapeText(item.credential_id)}">移除</button>
                </div>
            </div>`).join('');
        list.querySelectorAll('[data-passkey-rename]').forEach(btn => btn.addEventListener('click', () => renamePasskey(btn.dataset.passkeyRename)));
        list.querySelectorAll('[data-passkey-remove]').forEach(btn => btn.addEventListener('click', () => removePasskey(btn.dataset.passkeyRemove)));
    }

    function escapeText(value) {
        return String(value == null ? '' : value).replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
    }

    async function refresh() {
        if (!state.enabled) await loadPublicConfig();
        await loadAdminSettings();
        if (!state.enabled) {
            return;
        }
        try {
            const data = await jsonFetch('/api/admin/account/passkeys', { cache: 'no-store' });
            state.items = Array.isArray(data.items) ? data.items : [];
            state.stepUpValid = data.step_up_valid === true;
            renderDevices();
        } catch (error) {
            if (error.status !== 401) setMessage('passkeySecurityStatus', error.message, true);
        }
    }

    async function loadAdminSettings() {
        const card = document.getElementById('passkeyAdminSettingsCard');
        if (!card) return;
        try {
            const data = await jsonFetch('/api/admin/security/passkeys', { cache:'no-store' });
            card.style.display = data.is_super_admin ? '' : 'none';
            if (!data.is_super_admin) return;
            const enabled = document.getElementById('passkeyAdminEnabled');
            const origin = document.getElementById('passkeyAdminOrigin');
            const rpId = document.getElementById('passkeyAdminRpId');
            const maximum = document.getElementById('passkeyAdminMaxCredentials');
            const saveBtn = document.getElementById('passkeyAdminSaveBtn');
            if (enabled) {
                enabled.checked = data.enabled === true;
                enabled.disabled = data.enabled_managed_by_environment === true;
            }
            if (origin) origin.value = data.origin || data.public_base_url || '';
            if (rpId) rpId.value = data.rp_id || '';
            if (maximum) {
                maximum.value = Number(data.max_credentials_per_user || 10);
                maximum.disabled = data.max_managed_by_environment === true;
            }
            if (saveBtn) saveBtn.disabled = data.enabled_managed_by_environment === true;
            const status = document.getElementById('passkeyAdminStatusText');
            if (status) status.textContent = `当前状态：${data.enabled ? '已启用' : '未启用'}`;
            setMessage('passkeyAdminSettingsMsg', data.error || (data.enabled_managed_by_environment ? '当前由 Docker 环境变量管理。' : ''), !!data.error);
        } catch (error) {
            card.style.display = 'none';
        }
    }

    async function saveAdminSettings(event) {
        event.preventDefault();
        const btn = document.getElementById('passkeyAdminSaveBtn');
        if (btn) btn.disabled = true;
        setMessage('passkeyAdminSettingsMsg', '', false);
        try {
            const data = await jsonFetch('/api/admin/security/passkeys', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    enabled: !!document.getElementById('passkeyAdminEnabled')?.checked,
                    max_credentials_per_user: Number(document.getElementById('passkeyAdminMaxCredentials')?.value || 10)
                })
            });
            setMessage('passkeyAdminSettingsMsg', data.message || '设置已保存。', false);
            await loadPublicConfig();
            await loadAdminSettings();
            await refresh();
        } catch (error) {
            setMessage('passkeyAdminSettingsMsg', error.message, true);
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    function showStepUp(preferred) {
        const panel = document.getElementById('passkeyStepUpPanel');
        const passkeyBtn = document.getElementById('passkeyStepUpPasskeyBtn');
        if (panel) panel.hidden = false;
        if (passkeyBtn) passkeyBtn.hidden = preferred === 'email' || state.items.length === 0;
        setMessage('passkeyStepUpMsg', preferred === 'email' ? '请发送并填写安全邮箱验证码。' : '请使用已有 Passkey 或安全邮箱完成验证。', false);
    }

    async function verifyWithExistingPasskey() {
        try {
            const start = await jsonFetch('/api/admin/account/passkeys/verify/options', { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
            const credential = await navigator.credentials.get({ publicKey: prepareOptions(start.options) });
            await jsonFetch('/api/admin/account/passkeys/verify', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({ request_id:start.request_id, credential:serializeCredential(credential) })
            });
            state.stepUpValid = true;
            document.getElementById('passkeyStepUpPanel').hidden = true;
            setMessage('passkeyStepUpMsg', '安全验证通过。', false);
            await resumePendingAction();
        } catch (error) {
            setMessage('passkeyStepUpMsg', isUserCancellation(error) ? '已取消验证。' : error.message, !isUserCancellation(error));
        }
    }

    async function sendStepUpEmail() {
        try {
            const data = await jsonFetch('/api/admin/account/passkeys/confirm/email/send', { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
            setMessage('passkeyStepUpMsg', `验证码已发送到 ${data.email_masked || '安全邮箱'}。`, false);
        } catch (error) { setMessage('passkeyStepUpMsg', error.message, true); }
    }

    async function verifyStepUpEmail() {
        const code = String(document.getElementById('passkeyStepUpEmailCode')?.value || '').trim();
        if (!code) return setMessage('passkeyStepUpMsg', '请输入邮箱验证码。', true);
        try {
            await jsonFetch('/api/admin/account/passkeys/confirm/email/verify', {
                method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ code })
            });
            state.stepUpValid = true;
            document.getElementById('passkeyStepUpPanel').hidden = true;
            await resumePendingAction();
        } catch (error) { setMessage('passkeyStepUpMsg', error.message, true); }
    }

    async function resumePendingAction() {
        const action = state.pendingAction;
        state.pendingAction = null;
        if (typeof action === 'function') await action();
    }

    async function addPasskey() {
        const deviceName = window.prompt('请输入设备名称（例如：我的 MacBook 或工作手机）', `Passkey 设备 ${new Date().toLocaleDateString('zh-CN')}`);
        if (deviceName === null) return;
        try {
            const start = await jsonFetch('/api/admin/account/passkeys/register/options', { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
            const credential = await navigator.credentials.create({ publicKey: prepareOptions(start.options) });
            await jsonFetch('/api/admin/account/passkeys/register/verify', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({ request_id:start.request_id, device_name:deviceName, credential:serializeCredential(credential) })
            });
            setMessage('passkeySecurityStatus', 'Passkey 添加成功。', false);
            await refresh();
        } catch (error) {
            if (error.data && error.data.requires_step_up) {
                state.pendingAction = addPasskey;
                showStepUp(error.data.step_up_method);
                return;
            }
            if (!isUserCancellation(error)) setMessage('passkeySecurityStatus', error.message, true);
        }
    }

    async function renamePasskey(id) {
        const item = state.items.find(row => row.credential_id === id);
        const name = window.prompt('新的设备名称', item ? item.device_name : '');
        if (name === null) return;
        try {
            await jsonFetch(`/api/admin/account/passkeys/${encodeURIComponent(id)}`, {
                method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ device_name:name })
            });
            await refresh();
        } catch (error) { setMessage('passkeySecurityStatus', error.message, true); }
    }

    async function removePasskey(id) {
        if (!window.confirm('确定移除这个 Passkey 吗？移除后该设备将不能再用于登录。')) return;
        try {
            await jsonFetch(`/api/admin/account/passkeys/${encodeURIComponent(id)}`, { method:'DELETE' });
            await refresh();
        } catch (error) {
            if (error.data && error.data.requires_step_up) {
                state.pendingAction = () => removePasskey(id);
                showStepUp(state.items.length ? 'passkey' : 'email');
                return;
            }
            setMessage('passkeySecurityStatus', error.message, true);
        }
    }

    async function openSubaccountPasskeys(username) {
        try {
            const data = await jsonFetch(`/api/admin/subaccounts/${encodeURIComponent(username)}/passkeys`, { cache:'no-store' });
            const items = Array.isArray(data.items) ? data.items : [];
            let modal = document.getElementById('subaccountPasskeyModal');
            if (!modal) {
                modal = document.createElement('div');
                modal.id = 'subaccountPasskeyModal';
                modal.className = 'login-fail-modal';
                modal.innerHTML = '<div class="login-fail-dialog" role="dialog"><div class="login-fail-head"><span class="login-fail-icon"><i class="fas fa-fingerprint"></i></span><h3 id="subaccountPasskeyTitle"></h3></div><div id="subaccountPasskeyBody"></div><div class="login-fail-actions"><button type="button" class="login-fail-close-btn">关闭</button></div></div>';
                document.body.appendChild(modal);
                modal.querySelector('.login-fail-close-btn').addEventListener('click', () => { modal.hidden = true; });
            }
            modal.hidden = false;
            modal.querySelector('#subaccountPasskeyTitle').textContent = `${username} 的 Passkey`;
            const body = modal.querySelector('#subaccountPasskeyBody');
            body.innerHTML = items.length ? `<div style="text-align:right;margin-bottom:10px;"><button type="button" class="btn-sm btn-danger" data-force-revoke-all>吊销全部</button></div>` + items.map(item => `<div class="passkey-device-item"><div class="passkey-device-meta"><strong>${escapeText(item.device_name)}</strong><small>最近使用：${escapeText(formatTime(item.last_used_at))}</small></div><button type="button" class="btn-sm btn-danger" data-force-revoke="${escapeText(item.credential_id)}">吊销</button></div>`).join('') : '<p class="no-data">该子账号尚未绑定 Passkey。</p>';
            body.querySelectorAll('[data-force-revoke]').forEach(btn => btn.addEventListener('click', async () => {
                if (!window.confirm('确定强制吊销该子账号的 Passkey 吗？')) return;
                try {
                    await jsonFetch(`/api/admin/subaccounts/${encodeURIComponent(username)}/passkeys/${encodeURIComponent(btn.dataset.forceRevoke)}`, { method:'DELETE' });
                    await openSubaccountPasskeys(username);
                } catch (error) {
                    if (error.data && error.data.requires_step_up) {
                        modal.hidden = true;
                        state.pendingAction = () => openSubaccountPasskeys(username);
                        showStepUp(state.items.length ? 'passkey' : 'email');
                    } else window.alert(error.message);
                }
            }));
            body.querySelector('[data-force-revoke-all]')?.addEventListener('click', async () => {
                if (!window.confirm(`确定吊销 ${username} 的全部 Passkey 吗？`)) return;
                try {
                    await jsonFetch(`/api/admin/subaccounts/${encodeURIComponent(username)}/passkeys`, { method:'DELETE' });
                    await openSubaccountPasskeys(username);
                } catch (error) {
                    if (error.data && error.data.requires_step_up) {
                        modal.hidden = true;
                        state.pendingAction = () => openSubaccountPasskeys(username);
                        showStepUp(state.items.length ? 'passkey' : 'email');
                    } else window.alert(error.message);
                }
            });
        } catch (error) { window.alert(error.message); }
    }

    document.getElementById('passkeyLoginBtn')?.addEventListener('click', runPasskeyLogin);
    document.getElementById('passkeyAddBtn')?.addEventListener('click', addPasskey);
    document.getElementById('passkeyStepUpPasskeyBtn')?.addEventListener('click', verifyWithExistingPasskey);
    document.getElementById('passkeyStepUpEmailSendBtn')?.addEventListener('click', sendStepUpEmail);
    document.getElementById('passkeyStepUpEmailVerifyBtn')?.addEventListener('click', verifyStepUpEmail);
    document.getElementById('passkeyAdminSettingsForm')?.addEventListener('submit', saveAdminSettings);

    window.AdminPasskeys = { refresh, openSubaccountPasskeys, runPasskeyLogin };
    loadPublicConfig().then(refresh);
})();
