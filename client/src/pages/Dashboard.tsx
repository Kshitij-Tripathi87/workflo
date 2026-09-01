/**
 * Workflo QA Console begins in an intentional zero-data state. No synthetic runs,
 * metrics, identifiers, or timestamps appear before a workspace is connected.
 */
import { ArrowUpRight, FileCheck2, Plus, ShieldCheck, Terminal } from "lucide-react";
import { Link } from "wouter";
import { toast } from "sonner";

export default function Dashboard() {
  const explainSetup = () => toast.info("Connect an environment before creating the first test run.");

  return <main className="console-page console-page--empty">
    <aside className="console-rail">
      <div className="workspace-switcher"><span className="workspace-dot" /> Workflo workspace</div>
      <nav><a className="console-nav-active" href="#runs"><Terminal size={17} /> Runs</a><a href="#receipts"><FileCheck2 size={17} /> Receipts</a><a href="#policy"><ShieldCheck size={17} /> Policy</a></nav>
      <div className="console-rail-foot"><span>ENVIRONMENT</span><strong>Not connected</strong><Link href="/">← Exit console</Link></div>
    </aside>
    <section className="console-main" id="runs">
      <header className="console-header"><div><div className="console-kicker">CONTROL PLANE / READY</div><h1>Test runs</h1></div><button onClick={explainSetup} className="button button--signal button--small"><Plus size={16} /> New test run</button></header>
      <div className="console-setup-strip" aria-label="Workspace setup status"><div><span>ENVIRONMENT</span><strong>Awaiting connection</strong></div><div><span>RUN HISTORY</span><strong>Empty</strong></div><div><span>RECEIPTS</span><strong>Empty</strong></div></div>
      <section className="console-empty-panel" aria-label="Empty test run history"><div className="console-empty-panel__top"><span>RUN HISTORY</span><span>NO ACTIVITY</span></div><div className="console-empty-panel__body"><div className="console-empty-icon"><Terminal size={22} /></div><div><h2>No test runs yet.</h2><p>Connect an environment, define a verification target, then create the first run when you are ready.</p><div className="console-empty-panel__actions"><button type="button" onClick={explainSetup}>Create your first test run <Plus size={15} /></button><Link href="/docs#installation">Read installation guide <ArrowUpRight size={15} /></Link></div></div></div></section>
    </section>
    <aside className="receipt-inspector receipt-inspector--empty" id="receipts"><div className="inspector-top"><span>RECEIPT INSPECTOR</span></div><div className="console-empty-icon"><FileCheck2 size={21} /></div><strong>No receipt selected.</strong><p>Execution evidence appears here after the first test run is complete.</p><a href="#policy">Review execution policy <ArrowUpRight size={15} /></a><div id="policy" className="inspector-empty-policy"><span>POLICY STATUS</span><strong>Not configured</strong></div></aside>
  </main>;
}
