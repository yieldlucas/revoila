"""Génération de petits graphiques SVG inline (sans dépendance ni JS)."""
from __future__ import annotations


def bar_chart_svg(
    data: list[tuple[str, int]],
    width: int = 560,
    height: int = 140,
) -> str:
    """Histogramme SVG responsive à partir d'une liste (label, valeur).

    Le SVG utilise `currentColor` pour les barres : il s'adapte à la couleur
    du conteneur. Renvoie une chaîne prête à injecter (déjà sûre, pas d'input
    utilisateur). Si tout est à zéro, renvoie un état vide discret.
    """
    if not data:
        return _empty(width, height)

    values = [max(0, v) for _, v in data]
    peak = max(values)
    if peak == 0:
        return _empty(width, height)

    pad_x, pad_top, pad_bottom = 8, 12, 22
    plot_h = height - pad_top - pad_bottom
    plot_w = width - 2 * pad_x
    n = len(values)
    slot = plot_w / n
    bar_w = max(3.0, slot * 0.6)

    bars = []
    for i, (label, value) in enumerate(data):
        v = max(0, value)
        h = (v / peak) * plot_h
        x = pad_x + i * slot + (slot - bar_w) / 2
        y = pad_top + (plot_h - h)
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'rx="2" fill="currentColor"><title>{label} : {v}</title></rect>'
        )

    first, last = data[0][0], data[-1][0]
    baseline = pad_top + plot_h
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Envois par jour">'
        f'<line x1="{pad_x}" y1="{baseline:.1f}" x2="{width - pad_x}" '
        f'y2="{baseline:.1f}" stroke="#e6e6e6" stroke-width="1"/>'
        f'{"".join(bars)}'
        f'<text x="{pad_x}" y="{height - 6}" font-size="11" fill="#999">{first}</text>'
        f'<text x="{width - pad_x}" y="{height - 6}" font-size="11" fill="#999" '
        f'text-anchor="end">{last}</text>'
        f'<text x="{width/2:.0f}" y="{height - 6}" font-size="11" fill="#bbb" '
        f'text-anchor="middle">pic : {peak}/j</text>'
        f"</svg>"
    )


def _empty(width: int, height: int) -> str:
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        f'aria-label="Aucune donnée">'
        f'<text x="{width/2:.0f}" y="{height/2:.0f}" font-size="13" fill="#bbb" '
        f'text-anchor="middle">Aucun envoi sur la période</text></svg>'
    )
