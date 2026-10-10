import { usePalette } from "../theme";

function hexLum(hex) {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * Matrix as a table with sequential (one-hue) cell shading.
 * normalize="row" shades each cell by its share of the row (e.g. recall in a confusion matrix).
 */
export default function Heatmap({ rows, cols, matrix, rowLabel = (r) => r, colLabel = (c) => c, normalize = "row",
                                   format = (v) => v, corner = "", highlightDiagonal = false }) {
  const pal = usePalette();
  const max = Math.max(1, ...matrix.flat());
  return (
    <div className="table-wrap">
      <table style={{ width: "auto" }}>
        <thead>
          <tr>
            <th className="small muted">{corner}</th>
            {cols.map((c) => <th key={c} className="r small" style={{ whiteSpace: "normal", maxWidth: 90 }}>{colLabel(c)}</th>)}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => {
            const total = row.reduce((a, b) => a + b, 0) || 1;
            return (
              <tr key={rows[i]}>
                <td className="small" style={{ whiteSpace: "nowrap" }}>{rowLabel(rows[i])}</td>
                {row.map((v, j) => {
                  const share = normalize === "row" ? v / total : v / max;
                  const step = v === 0 ? -1 : Math.min(pal.seq.length - 1, Math.floor(share * pal.seq.length));
                  const bg = step < 0 ? "transparent" : pal.seq[step];
                  const ink = step < 0 ? "var(--muted)" : hexLum(bg) < 0.3 ? "#ffffff" : "#0b0b0b";
                  return (
                    <td key={j} className="r num" title={`${rowLabel(rows[i])} → ${colLabel(cols[j])}: ${v}${normalize === "row" ? ` (${(share * 100).toFixed(1)}% of row)` : ""}`}
                        style={{ background: bg, color: ink, minWidth: 52, border: `2px solid ${pal.surface}`,
                                 fontWeight: highlightDiagonal && i === j ? 600 : 400 }}>
                      {format(v, share)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
