(function () {
    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function normalizeLink(rawLink) {
        const link = String(rawLink || '').trim();
        if (!link) return '#';
        if (/^(?:https?:)?\/\//.test(link) || link.startsWith('/')) return link;
        return `/${link.replace(/^\.?\//, '')}`;
    }

    function getMeasurementSlug() {
        const pathname = window.location.pathname || '';
        const match = pathname.match(/\/pages\/measurement\/([^/?#]+?)(?:\.html)?$/i);
        return match ? match[1] : '';
    }

    function ensureStyles() {
        if (document.getElementById('measurement-recommendations-style')) return;
        const style = document.createElement('style');
        style.id = 'measurement-recommendations-style';
        style.textContent = `
            .measurement-recommendation-item {
                align-items: stretch;
            }
            .measurement-recommendation-item .eh-product-media {
                min-height: 220px;
                height: 220px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: linear-gradient(180deg, #f7fafc 0%, #eef4f8 100%);
                padding: 16px;
            }
            .measurement-recommendation-item .eh-product-media img {
                width: 100%;
                height: 100%;
                object-fit: contain;
                object-position: center;
                display: block;
            }
            .measurement-products-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 24px;
            }
            .measurement-product-card {
                display: flex;
                flex-direction: column;
                background: #fff;
                border: 1px solid rgba(15, 45, 80, 0.08);
                border-radius: 18px;
                box-shadow: 0 12px 28px rgba(15, 45, 80, 0.08);
                overflow: hidden;
                min-height: 100%;
            }
            .measurement-product-card__media {
                background: linear-gradient(180deg, #f7fafc 0%, #eef4f8 100%);
                aspect-ratio: 16 / 10;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
            }
            .measurement-product-card__media img {
                width: 100%;
                height: 100%;
                object-fit: contain;
                display: block;
            }
            .measurement-product-card__body {
                display: flex;
                flex: 1;
                flex-direction: column;
                padding: 20px;
            }
            .measurement-product-card__title {
                margin: 0 0 12px;
                font-size: 22px;
                line-height: 1.35;
                color: #12344d;
            }
            .measurement-product-card__desc {
                margin: 0;
                color: #52667a;
                line-height: 1.7;
            }
            .measurement-product-card__footer {
                margin-top: 18px;
            }
            .measurement-product-link {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 112px;
                padding: 10px 18px;
                border-radius: 999px;
                background: #0f5f8f;
                color: #fff !important;
                text-decoration: none;
                font-weight: 600;
                transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
            }
            .measurement-product-link:hover {
                background: #0c4d74;
                box-shadow: 0 8px 18px rgba(15, 95, 143, 0.22);
                transform: translateY(-1px);
            }
            @media (max-width: 768px) {
                .measurement-recommendation-item {
                    align-items: center;
                }
                .measurement-recommendation-item .eh-product-media {
                    min-height: 180px;
                    height: 180px;
                }
                .measurement-products-grid {
                    gap: 18px;
                }
                .measurement-product-card__body {
                    padding: 18px;
                }
                .measurement-product-card__title {
                    font-size: 20px;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function buildEhItems(items) {
        return items.map((item, idx) => {
            const link = normalizeLink(item.link);
            const image = item.image
                ? `<img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.title || '产品')}">`
                : '<div style="color:#8aa0b4; font-size:14px;">暂无图片</div>';
            return `
                <article class="eh-product eh-reveal measurement-recommendation-item" data-delay="${Math.min(idx + 1, 4)}">
                    <div class="eh-product-media">${image}</div>
                    <div>
                        <h3>${escapeHtml(item.title || '')}</h3>
                        <p>${escapeHtml(item.desc || '')}</p>
                        <div class="measurement-product-card__footer">
                            <a class="measurement-product-link" href="${escapeHtml(link)}">查看详情</a>
                        </div>
                    </div>
                </article>
            `;
        }).join('');
    }

    function buildGridItems(items) {
        return `
            <div class="measurement-products-grid">
                ${items.map(item => {
                    const link = normalizeLink(item.link);
                    const media = item.image
                        ? `<img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.title || '产品')}">`
                        : '<div style="color:#8aa0b4; font-size:14px;">暂无图片</div>';
                    return `
                        <article class="measurement-product-card">
                            <div class="measurement-product-card__media">${media}</div>
                            <div class="measurement-product-card__body">
                                <h3 class="measurement-product-card__title">${escapeHtml(item.title || '')}</h3>
                                <p class="measurement-product-card__desc">${escapeHtml(item.desc || '')}</p>
                                <div class="measurement-product-card__footer">
                                    <a class="measurement-product-link" href="${escapeHtml(link)}">查看详情</a>
                                </div>
                            </div>
                        </article>
                    `;
                }).join('')}
            </div>
        `;
    }

    function renderRecommendations(items) {
        if (!Array.isArray(items) || !items.length) return;
        ensureStyles();

        const ehProducts = document.querySelector('.eh-products');
        if (ehProducts) {
            ehProducts.innerHTML = buildEhItems(items);
            return;
        }

        const productsSection = document.getElementById('products');
        if (productsSection) {
            const sectionContainer = productsSection.querySelector('.vs-container') || productsSection;
            const titleSection = sectionContainer.querySelector('.vs-section-title-centered');
            const titleHtml = titleSection
                ? titleSection.outerHTML
                : '<div class="vs-section-title-centered"><h2>推荐产品方案</h2></div>';
            sectionContainer.innerHTML = `${titleHtml}${buildGridItems(items)}`;
            return;
        }

        const main = document.querySelector('main');
        if (!main) return;
        main.insertAdjacentHTML('beforeend', `
            <section class="vs-content-section" id="products" style="padding-top: 40px;">
                <div class="vs-container">
                    <div class="vs-section-title-centered"><h2>推荐产品方案</h2></div>
                    ${buildGridItems(items)}
                </div>
            </section>
        `);
    }

    function loadRecommendations() {
        const slug = getMeasurementSlug();
        if (!slug) return;

        fetch(`/api/h2-home/measurement-products?slug=${encodeURIComponent(slug)}`)
            .then(res => res.json())
            .then(data => renderRecommendations(data.items || []))
            .catch(error => {
                console.error('Failed to load measurement recommendations:', error);
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadRecommendations);
    } else {
        loadRecommendations();
    }
})();
