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

    function toSubscriptDigits(digits) {
        return String(digits || '').replace(/[0-9]/g, function (d) {
            return SUBSCRIPT_MAP[d] || d;
        });
    }

    function isModelCodeContext(source, start, end) {
        var prev = start > 0 ? source.charAt(start - 1) : '';
        var next = end < source.length ? source.charAt(end) : '';
        if (prev !== '-' && next !== '-') return false;

        var spanStart = start;
        while (spanStart > 0 && /[A-Za-z0-9-]/.test(source.charAt(spanStart - 1))) {
            spanStart--;
        }
        var spanEnd = end;
        while (spanEnd < source.length && /[A-Za-z0-9-]/.test(source.charAt(spanEnd))) {
            spanEnd++;
        }

        var span = source.slice(spanStart, spanEnd);
        if (span.indexOf('-') === -1) return false;

        var segments = span.split('-').filter(function (s) { return !!s; });
        if (segments.length < 2) return false;

        // Treat as product model code when any segment is uppercase letters without digits,
        // e.g. MC-LD-PH2 / LD-H2 / MC-TD-01.
        return segments.some(function (seg) {
            return /^[A-Z]{2,}$/.test(seg);
        });
    }

    function convertChemicalFormulaText(text) {
        var source = String(text || '');
        if (!/[A-Z]/.test(source) || !/[0-9]/.test(source)) return source;
        // Convert formulas like H2, N2, CO2, Al2O3, H2S, 95%N2+5%H2.
        return source.replace(/\b(?:[A-Z][a-z]?\d*)+\b/g, function (token, offset) {
            if (!/[0-9]/.test(token)) return token;
            var end = offset + token.length;
            if (isModelCodeContext(source, offset, end)) return token;
            return token.replace(/([A-Z][a-z]?)(\d+)/g, function (_, element, digits) {
                return element + toSubscriptDigits(digits);
            });
        });
    }

    function shouldSkipNode(node) {
        if (!node || !node.parentElement) return true;
        var parent = node.parentElement;
        if (parent.closest('script,style,textarea,code,pre,kbd,samp,svg,math')) return true;
        if (parent.isContentEditable) return true;
        return false;
    }

    function processTextNode(node) {
        if (!node || !node.nodeValue || shouldSkipNode(node)) return;
        if (!/[A-Z]/.test(node.nodeValue) || !/[0-9]/.test(node.nodeValue)) return;
        var updated = convertChemicalFormulaText(node.nodeValue);
        if (updated !== node.nodeValue) {
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
