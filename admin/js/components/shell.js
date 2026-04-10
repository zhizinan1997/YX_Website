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

    function regroupSidebar() {
        const menu = document.querySelector('#dashboard .sidebar-menu');
        const state = window.Admin2State;
        if (!menu || !state || menu.dataset.admin2Grouped === '1') return;

        const sections = [];
        for (const sectionDef of state.shellSections || []) {
            const sectionEl = document.createElement('section');
            sectionEl.className = 'sidebar-section';

            const labelEl = document.createElement('div');
            labelEl.className = 'sidebar-section-label';
            labelEl.textContent = sectionDef.label;
            sectionEl.appendChild(labelEl);

            const bodyEl = document.createElement('div');
            bodyEl.className = 'sidebar-section-body';

            for (const item of sectionDef.items || []) {
                const node = resolveNode(item);
                if (node) bodyEl.appendChild(node);
            }

            if (bodyEl.children.length > 0) {
                sectionEl.appendChild(bodyEl);
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
        enhanceTopBar();
    }

    window.Admin2Shell = {
        mount,
    };
})();
