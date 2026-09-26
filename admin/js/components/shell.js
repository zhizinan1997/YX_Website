(function () {
    function resolveNode(item) {
        if (!item) return null;
        if (item.type === 'selector') {
            return document.querySelector(item.key);
        }
        if (item.type === 'group') {
            return document.querySelector(`.sidebar-menu-group[data-menu-group="${item.key}"]`);
        }
        return document.querySelector(`.menu-item[data-view="${item.key}"]`);
    }

    function setSectionCollapsed(sectionEl, collapsed) {
        if (!sectionEl) return;
        const isCollapsed = !!collapsed;
        const bodyEl = sectionEl.querySelector('.sidebar-section-body');
        const toggleEl = sectionEl.querySelector('.sidebar-section-toggle');
        sectionEl.classList.toggle('is-collapsed', isCollapsed);
        if (bodyEl) bodyEl.hidden = isCollapsed;
        if (toggleEl) {
            toggleEl.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
        }
    }

    function toggleSection(sectionEl) {
        if (!sectionEl) return;
        setSectionCollapsed(sectionEl, !sectionEl.classList.contains('is-collapsed'));
    }

    function revealViewSection(viewName) {
        const key = String(viewName || '').trim();
        if (!key) return;
        const menuView = ['settings', 'log-records', 'site-settings'].includes(key)
            ? 'system-management'
            : ['chatbot', 'chatbot-knowledge', 'chatbot-history'].includes(key)
                ? 'ai-management'
                : key;
        const menuItem = document.querySelector(`.menu-item[data-view="${key}"]`)
            || document.querySelector(`.menu-item[data-view="${menuView}"]`);
        const sectionEl = menuItem && menuItem.closest('.sidebar-section');
        if (sectionEl && sectionEl.classList.contains('is-collapsed')) {
            setSectionCollapsed(sectionEl, false);
        }
    }

    function regroupSidebar() {
        const menu = document.querySelector('#dashboard .sidebar-menu');
        const state = window.Admin2State;
        if (!menu || !state || menu.dataset.admin2Grouped === '1') return;

        const sections = [];
        for (const sectionDef of state.shellSections || []) {
            const sectionEl = document.createElement('section');
            sectionEl.className = 'sidebar-section';
            sectionEl.dataset.sectionKey = sectionDef.key || sectionDef.label;

            const toggleEl = document.createElement('button');
            toggleEl.type = 'button';
            toggleEl.className = 'sidebar-section-toggle';
            toggleEl.setAttribute('aria-expanded', 'true');
            toggleEl.innerHTML = `<span>${sectionDef.label}</span><i class="fas fa-chevron-down sidebar-section-caret" aria-hidden="true"></i>`;
            toggleEl.addEventListener('click', () => toggleSection(sectionEl));
            sectionEl.appendChild(toggleEl);

            const bodyEl = document.createElement('div');
            bodyEl.className = 'sidebar-section-body';

            for (const item of sectionDef.items || []) {
                const node = resolveNode(item);
                if (node) bodyEl.appendChild(node);
            }

            if (bodyEl.children.length > 0) {
                sectionEl.appendChild(bodyEl);
                setSectionCollapsed(sectionEl, false);
                sections.push(sectionEl);
            }
        }

        if (sections.length) {
            menu.replaceChildren(...sections);
            menu.dataset.admin2Grouped = '1';
        }
    }

    function enhanceTopBar() {
        return;
    }

    function mount() {
        regroupSidebar();
        const activeMenuItem = document.querySelector('.menu-item[data-view].active');
        const activeView = document.querySelector('.view-section.active');
        if (activeView && activeView.id) {
            revealViewSection(activeView.id.replace(/^view-/, ''));
        } else if (activeMenuItem) {
            revealViewSection(activeMenuItem.dataset.view);
        }
        enhanceTopBar();
    }

    window.Admin2Shell = {
        mount,
        revealViewSection,
    };
})();
