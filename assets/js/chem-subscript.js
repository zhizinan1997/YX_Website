(function () {
    'use strict';

    var SUBSCRIPT_MAP = {
        '0': '\u2080',
        '1': '\u2081',
        '2': '\u2082',
        '3': '\u2083',
        '4': '\u2084',
        '5': '\u2085',
        '6': '\u2086',
        '7': '\u2087',
        '8': '\u2088',
        '9': '\u2089'
    };

    // Whitelist of known chemical formulas that should have subscripted digits.
    // Sorted longest-first so longer formulas match before shorter ones.
    var FORMULAS = [
        'Al2O3', 'CaCO3', 'Ca(OH)2', 'CaO2',
        'C2H2', 'C2H4', 'C2H5OH', 'C2H6', 'C2H6O', 'C3H8', 'C4H10', 'C6H6',
        'CH2O', 'CH3OH', 'CH4',
        'ClO2', 'Cl2',
        'CO2', 'CO3',
        'CrO3', 'Cr2O3',
        'Cu2O', 'CuO',
        'Fe2O3', 'Fe3O4', 'FeO',
        'GeH4',
        'HBr', 'HCl', 'HCN', 'HF', 'HI',
        'H2', 'H2O2', 'H2O', 'H2S', 'H2SO4', 'H3PO4',
        'MgO', 'MnO2', 'Mn2O3',
        'NaCl', 'Na2CO3', 'Na2O', 'NaOH',
        'N2', 'N2O', 'N2O4', 'N2O5',
        'NH3', 'NH4',
        'NO2', 'NO3', 'NOx', 'NOX',
        'O2', 'O3',
        'PH3', 'PCl3', 'PCl5',
        'SF6', 'SiH4', 'SiO2',
        'SnO2',
        'SO2', 'SO3', 'SOx', 'SOX', 'SO2F2',
        'TiO2',
        'VOC', 'V2O5',
        'WO3',
        'ZnO', 'ZrO2'
    ];

    // Sort longest first to avoid partial matches
    FORMULAS.sort(function (a, b) { return b.length - a.length; });

    // Build a single regex that matches any formula from the whitelist,
    // bounded so it won't match inside longer words/codes.
    // We use a negative lookbehind for word chars and a negative lookahead for word chars.
    var escapedFormulas = FORMULAS.map(function (f) {
        return f.replace(/([().])/g, '\\$1');
    });
    var FORMULA_RE = new RegExp('(?<![A-Za-z0-9_-])(' + escapedFormulas.join('|') + ')(?![A-Za-z0-9_-])', 'g');

    function toSubscriptDigits(digits) {
        return String(digits || '').replace(/[0-9]/g, function (d) {
            return SUBSCRIPT_MAP[d] || d;
        });
    }

    function subscriptFormula(formula) {
        // Only subscript digits that follow element symbols
        return formula.replace(/([A-Z][a-z]?)(\d+)/g, function (_, element, digits) {
            return element + toSubscriptDigits(digits);
        });
    }

    function convertText(text) {
        var source = String(text || '');
        if (!/[0-9]/.test(source)) return source;
        return source.replace(FORMULA_RE, function (match) {
            return subscriptFormula(match);
        });
    }

    function shouldSkipNode(node) {
        if (!node || !node.parentElement) return true;
        var parent = node.parentElement;
        if (parent.closest('script,style,textarea,code,pre,kbd,samp,svg,math,input,select')) return true;
        if (parent.isContentEditable) return true;
        return false;
    }

    function processTextNode(node) {
        if (!node || !node.nodeValue || shouldSkipNode(node)) return;
        var text = node.nodeValue;
        if (!/[0-9]/.test(text)) return;
        var updated = convertText(text);
        if (updated !== text) {
            node.nodeValue = updated;
        }
    }

    function processNodeTree(rootNode) {
        if (!rootNode) return;
        if (rootNode.nodeType === 3) {
            processTextNode(rootNode);
            return;
        }
        if (rootNode.nodeType !== 1) return;
        var walker = document.createTreeWalker(rootNode, NodeFilter.SHOW_TEXT);
        var current;
        while ((current = walker.nextNode())) {
            processTextNode(current);
        }
    }

    function initChemicalSubscript() {
        if (window.__mcChemSubscriptInitialized) return;
        window.__mcChemSubscriptInitialized = true;

        processNodeTree(document.body);

        if (!window.MutationObserver || !document.body) return;
        var observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (m) {
                if (m.type === 'characterData') {
                    processTextNode(m.target);
                    return;
                }
                if (!m.addedNodes || !m.addedNodes.length) return;
                for (var i = 0; i < m.addedNodes.length; i++) {
                    processNodeTree(m.addedNodes[i]);
                }
            });
        });
        observer.observe(document.body, {
            subtree: true,
            childList: true,
            characterData: true
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initChemicalSubscript);
    } else {
        initChemicalSubscript();
    }
})();
