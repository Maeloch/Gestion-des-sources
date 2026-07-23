/* Tri générique des tableaux par en-tête de colonne cliquable.
 *
 * Utilisation dans un template :
 *   <th data-sort-key="nom" data-sort-type="text">Nom</th>
 *   <tr data-sort-nom="valeur à trier">...</tr>
 *
 * data-sort-type vaut "text" (défaut, tri alphabétique) ou "number" (tri
 * numérique). La valeur triée est lue depuis l'attribut data-sort-{clé}
 * de la ligne <tr> elle-même, PAS depuis le texte affiché dans la
 * cellule -- ça permet de trier par exemple sur une activité brute en Bq
 * même si la cellule affiche "148 MBq" pour l'œil humain.
 *
 * Appeler rendreTableTriable('monTableauId') une fois le tableau rendu.
 */
function rendreTableTriable(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const headers = table.querySelectorAll('thead th[data-sort-key]');
    let colonneActive = null;
    let sensActif = 'asc';

    headers.forEach(th => {
        th.classList.add('sortable-th');
        th.addEventListener('click', () => {
            const cle = th.dataset.sortKey;
            const type = th.dataset.sortType || 'text';
            sensActif = (colonneActive === cle && sensActif === 'asc') ? 'desc' : 'asc';
            colonneActive = cle;

            // dataset['sort' + cle] est FAUX : data-sort-id devient
            // dataset.sortId (camelCase, première lettre après "sort" en
            // majuscule), pas dataset.sortid. Bug trouvé le 12/07/2026 :
            // la comparaison tombait toujours sur undefined des deux
            // côtés, donc aucune ligne ne bougeait, alors que le clic et
            // la flèche fonctionnaient (eux ne dépendent pas de cette
            // valeur) -- d'où le symptôme "la flèche change mais pas les
            // lignes", identique sur tous les tableaux (même fonction
            // partagée).
            const cleDataset = 'sort' + cle.charAt(0).toUpperCase() + cle.slice(1);

            const tbody = table.querySelector('tbody');
            const lignes = Array.from(tbody.querySelectorAll('tr'));
            lignes.sort((a, b) => {
                let va = a.dataset[cleDataset] ?? '';
                let vb = b.dataset[cleDataset] ?? '';
                if (type === 'number') {
                    va = va === '' ? -Infinity : parseFloat(va);
                    vb = vb === '' ? -Infinity : parseFloat(vb);
                    return sensActif === 'asc' ? va - vb : vb - va;
                }
                va = va.toLowerCase();
                vb = vb.toLowerCase();
                return sensActif === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            });
            lignes.forEach(l => tbody.appendChild(l));

            headers.forEach(h => h.classList.remove('sorted-asc', 'sorted-desc'));
            th.classList.add(sensActif === 'asc' ? 'sorted-asc' : 'sorted-desc');

            // Redéclenche la pagination (si ce tableau en a une) : les
            // lignes ont changé d'ordre, la page affichée doit se
            // recalculer sur ce nouvel ordre -- voir paginate.js.
            window.PaginationRefresh && window.PaginationRefresh[tableId] && window.PaginationRefresh[tableId]();
        });
    });
}
