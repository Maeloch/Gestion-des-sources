/* Pagination générique des tableaux, coopérant avec le tri (sortable.js)
 * et les filtres déjà en place sur certaines pages (onglets, cases à
 * cocher...), sans jamais les court-circuiter.
 *
 * Principe : chaque ligne porte un marqueur dédié, `data-filtre-ok`
 * ("true" ou "false"), DISTINCT de style.display -- indispensable :
 * style.display est aussi manipulé par la pagination elle-même pour
 * masquer les lignes hors-page, donc l'utiliser pour ALSO représenter
 * "exclu par le filtre" créerait une confusion entre les deux couches
 * (bug trouvé le 13/07/2026 en testant : après un changement de taille
 * de page, le total affiché rétrécissait au lieu de rester stable,
 * parce que les lignes déjà masquées par la pagination précédente
 * étaient prises à tort pour des lignes exclues par le filtre).
 *
 * Toute page qui a son propre filtre (ex: sources.html, audit.html) doit
 * positionner row.dataset.filtreOk = 'true'/'false' sur CHAQUE ligne
 * selon ses propres critères, PUIS appeler
 * window.PaginationRefresh['monTableauId']?.() à la toute fin de sa
 * fonction de filtre. La pagination affiche alors seulement la page
 * courante PARMI les lignes marquées 'true', en masquant les autres à
 * leur tour via style.display -- sans jamais toucher au marqueur
 * lui-même.
 *
 * Pour un tableau SANS filtre existant (radionucléides, mouvements,
 * lieux, consommations), rien à faire de spécial : une ligne sans
 * marqueur du tout est considérée éligible par défaut.
 *
 * Après un tri (sortable.js), la page courante est conservée (pas de
 * retour à la page 1) : ce sont les mêmes lignes, juste dans un autre
 * ordre, donc rester à "la page 3" garde un sens pour l'utilisateur.
 *
 * Utilisation dans un template : rendrePaginable('monTableauId');
 */
const _paginationState = {};

function rendrePaginable(tableId, tailleParDefaut = 20) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const controles = document.createElement('div');
    controles.className = 'pagination-controls';
    controles.innerHTML = `
        <div class="pagination-taille">
            Afficher
            <select id="${tableId}_pageSize">
                <option value="10">10</option>
                <option value="20">20</option>
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="all">Tout</option>
            </select>
            par page
        </div>
        <div class="pagination-nav">
            <button type="button" id="${tableId}_prevPage" aria-label="Page précédente">&laquo; Précédent</button>
            <span id="${tableId}_pageInfo" class="pagination-info"></span>
            <button type="button" id="${tableId}_nextPage" aria-label="Page suivante">Suivant &raquo;</button>
        </div>
    `;
    table.insertAdjacentElement('afterend', controles);

    document.getElementById(`${tableId}_pageSize`).value = String(tailleParDefaut);
    _paginationState[tableId] = { page: 1, pageSize: tailleParDefaut };

    function refresh() {
        const state = _paginationState[tableId];
        const toutesLignes = Array.from(tbody.querySelectorAll('tr'));
        const eligibles = toutesLignes.filter(r => r.dataset.filtreOk !== 'false');

        const taille = state.pageSize === 'all' ? Math.max(eligibles.length, 1) : state.pageSize;
        const totalPages = Math.max(1, Math.ceil(eligibles.length / taille));
        state.page = Math.min(Math.max(state.page, 1), totalPages);

        const debut = (state.page - 1) * taille;
        const fin = debut + taille;
        const aAfficher = new Set(eligibles.slice(debut, fin));

        toutesLignes.forEach(r => {
            if (r.dataset.filtreOk === 'false') { r.style.display = 'none'; return; }
            r.style.display = aAfficher.has(r) ? '' : 'none';
        });

        const info = document.getElementById(`${tableId}_pageInfo`);
        const prevBtn = document.getElementById(`${tableId}_prevPage`);
        const nextBtn = document.getElementById(`${tableId}_nextPage`);
        if (info) {
            info.textContent = eligibles.length === 0
                ? ''
                : `Page ${state.page} / ${totalPages} (${eligibles.length} au total)`;
        }
        if (prevBtn) prevBtn.disabled = state.page <= 1;
        if (nextBtn) nextBtn.disabled = state.page >= totalPages;
        controles.style.display = eligibles.length === 0 ? 'none' : 'flex';
    }

    document.getElementById(`${tableId}_pageSize`).addEventListener('change', (e) => {
        _paginationState[tableId].pageSize = e.target.value === 'all' ? 'all' : parseInt(e.target.value, 10);
        _paginationState[tableId].page = 1;
        refresh();
    });
    document.getElementById(`${tableId}_prevPage`).addEventListener('click', () => {
        _paginationState[tableId].page--;
        refresh();
    });
    document.getElementById(`${tableId}_nextPage`).addEventListener('click', () => {
        _paginationState[tableId].page++;
        refresh();
    });

    window.PaginationRefresh = window.PaginationRefresh || {};
    window.PaginationRefresh[tableId] = refresh;

    refresh();
}
