/* Recherche libre générique sur un tableau -- demandé le 14/07/2026 :
 * généraliser à toutes les pages la logique de recherche déjà en place
 * sur Sources.
 *
 * Principe : chaque ligne porte déjà des attributs data-sort-* pour le
 * tri (voir sortable.js) -- cette recherche les réutilise TELS QUELS,
 * sans liste de colonnes à maintenir à la main par page : un texte tapé
 * est comparé à TOUTES les valeurs data-sort-* de la ligne, insensible à
 * la casse. Ça marche automatiquement sur n'importe quel tableau déjà
 * équipé pour le tri, sans code spécifique par page.
 *
 * Deux façons de l'utiliser :
 *
 * 1. Page SANS filtre déjà en place (Radionucléides, Mouvements, Lieux,
 *    Consommations) : un seul appel suffit, il crée le champ de
 *    recherche et branche tout seul.
 *
 *        rendreFiltrable('monTableauId');
 *
 * 2. Page AVEC un filtre déjà en place (Sources, Audit) qui doit
 *    COMBINER plusieurs critères : utiliser texteCorrespond(row, texte)
 *    comme brique dans la fonction de filtre existante, plutôt que
 *    d'appeler rendreFiltrable (qui positionnerait data-filtre-ok tout
 *    seul, en écrasant les autres critères déjà calculés).
 */

function texteCorrespond(row, texte) {
    if (!texte) return true;
    texte = texte.toLowerCase();
    const matchDataset = Object.entries(row.dataset).some(
        ([cle, valeur]) => cle !== 'filtreOk' && String(valeur).toLowerCase().includes(texte)
    );
    if (matchDataset) return true;
    // Repli sur le texte visible de la ligne : certaines pages (Audit)
    // n'exposent l'information recherchable (source, utilisateur, champ
    // modifié...) que dans le contenu des cellules, pas en attribut
    // data-*. Trouvé le 14/07/2026 en testant : une recherche par
    // identifiant de source ne trouvait rien sur Audit alors que le nom
    // de la source y est bien affiché.
    return row.textContent.toLowerCase().includes(texte);
}

function rendreFiltrable(tableId, options = {}) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const barre = document.createElement('div');
    barre.className = 'recherche-libre';
    barre.innerHTML = `<input type="text" id="${tableId}_recherche" placeholder="${options.placeholder || '🔎 Rechercher...'}" autocomplete="off">`;
    table.insertAdjacentElement('beforebegin', barre);

    const champ = document.getElementById(`${tableId}_recherche`);

    // Préremplissage depuis ?recherche=XXX dans l'URL -- demandé le
    // 28/07/2026, pour permettre un lien direct depuis une autre page
    // (ex: cliquer sur un identifiant de source dans le tableau
    // Radionucléides doit amener sur Sources avec ce texte déjà
    // recherché, sans avoir à le retaper).
    const params = new URLSearchParams(window.location.search);
    const rechercheDepuisUrl = params.get('recherche');
    if (rechercheDepuisUrl) champ.value = rechercheDepuisUrl;

    function refresh() {
        const texte = champ.value.trim();
        Array.from(tbody.querySelectorAll('tr')).forEach(row => {
            row.dataset.filtreOk = texteCorrespond(row, texte) ? 'true' : 'false';
        });
        window.PaginationRefresh && window.PaginationRefresh[tableId] && window.PaginationRefresh[tableId]();
    }

    champ.addEventListener('input', refresh);

    window.FiltrableRefresh = window.FiltrableRefresh || {};
    window.FiltrableRefresh[tableId] = refresh;

    refresh();
}
