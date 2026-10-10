import { useState } from "react";
import { api, useApi } from "../api";
import { Async, Card, Meter, Segmented, Tile } from "../components/ui";
import { fmtInt } from "../format";
import { usePalette } from "../theme";
import { RunTable } from "./Runs";

const SORTS = [
  { value: "uncertainty", label: "Most informative" },
  { value: "risk", label: "Highest risk" },
  { value: "recent", label: "Most recent" },
];

export default function Review() {
  const [sort, setSort] = useState("uncertainty");
  const state = useApi(`/api/review-queue?sort=${sort}&limit=50`, { refreshMs: 15000 });
  const models = useApi("/api/models", { refreshMs: 10000 });
  const pal = usePalette();
  const [msg, setMsg] = useState(null);

  const retrain = async () => {
    const r = await api("/api/models/retrain", { method: "POST" });
    setMsg(r.message);
    models.reload();
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Review queue</h1>
          <p>
            Flagged runs waiting for a human verdict. Each review does two things: the outcome immediately rewards the
            intervention policy, and the label is used to retrain the failure classifier. “Most informative” orders runs by
            classifier uncertainty (active learning), so each label improves the model as much as possible.
          </p>
        </div>
        <div className="row">
          {msg && <span className="small text-2">{msg}</span>}
          <button onClick={retrain} disabled={models.data?.retraining}>{models.data?.retraining ? "Retraining…" : "Retrain now"}</button>
        </div>
      </div>
      <Async state={state}>
        {(d) => (
          <>
            <div className="tiles">
              <Tile label="Awaiting review" value={fmtInt(d.total)} />
              <Tile label="Labels collected" value={fmtInt(d.labels_total)} />
              <Tile label="Labels not yet in a model" value={fmtInt(d.labels_not_yet_trained)} delta="used by the next retrain" />
            </div>
            <Card flush title="Runs to review" right={<div style={{ paddingRight: 16 }}><Segmented options={SORTS} value={sort} onChange={setSort} /></div>}>
              <RunTable rows={d.items} extra={{
                label: "Uncertainty",
                render: (r) => (
                  <div className="row" style={{ flexWrap: "nowrap" }} title="Normalized entropy of the classifier's probabilities">
                    <Meter value={r.uncertainty} color={pal.series[6]} width={50} /><span className="small num">{r.uncertainty.toFixed(2)}</span>
                  </div>
                ),
              }} />
            </Card>
          </>
        )}
      </Async>
    </>
  );
}
