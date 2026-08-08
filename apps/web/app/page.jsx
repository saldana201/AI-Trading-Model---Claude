import Chat from "../components/Chat";
import Assistant from "../components/Assistant";
import Explorer from "../components/Explorer";
import Settings from "../components/Settings";
import { LiveTicker, LiveFeed, ArmButton, SnapshotRefresher } from "../components/Live";
import { BenchmarkStrip, CalibrationPanel } from "../components/Honest";
import {
  RegimeStrip, VixPanel, IndexPanel, TapePanel,
  OptionsPanel, RotationTable, SetupCards, JournalPanel,
} from "../components/panels";

export const dynamic = "force-dynamic";

const API = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getSnapshot() {
  try {
    const r = await fetch(`${API}/api/snapshot`, { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    return await r.json();
  } catch {
    return null;
  }
}

async function getJournal() {
  try {
    const r = await fetch(`${API}/api/journal`, { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    return await r.json();
  } catch {
    return null;
  }
}

/* Tier divider — an eyebrow label with a hairline rule. */
function Tier({ label, note }) {
  return (
    <div className="tier">
      <span className="tier-label">{label}</span>
      {note && <span className="tier-note">{note}</span>}
      <span className="tier-rule" />
    </div>
  );
}

export default async function Page() {
  const [d, journal] = await Promise.all([getSnapshot(), getJournal()]);
  return (
    <div className="wrap">
      <header>
        <div className="mark">CONFLUENCE<b>.</b></div>
        <div className="sub">pre-market command surface</div>
        <div className="meta">
          <span className="chip">{d ? `${d.source} data` : "api offline"}</span>
          <span className="num">{d ? (d.generated_at || "").slice(0, 16) : ""}</span>
          <SnapshotRefresher />
        </div>
      </header>

      {!d ? (
        <div className="notrade" style={{ marginTop: 18 }}>
          <b>API offline.</b> Start the gateway, then reload:&nbsp;
          <span className="num">CONFLUENCE_DATA=synthetic uvicorn apps.api.main:app --port 8000</span>
        </div>
      ) : (
        <>
          <LiveTicker />

          {/* ---- Tier 1 · the answer ---- */}
          <Tier label="The answer" />
          <RegimeStrip regime={d.regime} />
          <BenchmarkStrip />

          {/* ---- Tier 2 · today's output ---- */}
          <Tier label="Today's output" />
          <section className="tier2">
            <div>
              <SetupCards setups={d.setups} />
              <ArmButton />
            </div>
            <LiveFeed initial={d.alert_feed} />
          </section>

          {/* ---- Tier 3 · evidence (demoted; hover to bring forward, click ⓘ to read) ---- */}
          <Tier label="Evidence" note="demoted — hover to focus, click ⓘ to read the numbers" />
          <div className="demoted">
            <main>
              <VixPanel vix={d.vix} />
              <IndexPanel symbol="QQQ" data={d.indices.QQQ} />
              <TapePanel qqq={d.indices.QQQ} spy={d.indices.SPY} />
            </main>
            {d.options?.QQQ && (
              <section className="rowopt">
                <OptionsPanel gex={d.options.QQQ} />
                <IndexPanel symbol="SPY" data={d.indices.SPY} />
              </section>
            )}
            <RotationTable rotation={d.rotation} />
            {journal && <JournalPanel journal={journal} />}
            <CalibrationPanel />
            <Explorer />
            <Assistant />
            <Settings />
          </div>
        </>
      )}

      <Chat />

      <footer>
        Levels are Williams-fractal clusters weighted by recency and touches; regime is a
        rules-first weighted composite — every number traces to engine evidence.
        Decision-support tooling, not investment advice.
      </footer>
    </div>
  );
}
