/**
 * Minimal Workflo hero — a single immersive runtime surface with only the product thesis
 * and the two essential routes. The interactive sandbox fills the complete viewport.
 */
import { useEffect, useRef, useState, type FormEvent, type PointerEvent } from "react";
import { ArrowUpRight, CircleCheckBig } from "lucide-react";
import { Link } from "wouter";
import { WORKFLO_HERO } from "@/lib/workfloHero";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";

const WORK_EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Home() {
  const headlineTagline = WORKFLO_HERO.tagline;
  const [heroImageLoaded, setHeroImageLoaded] = useState(false);
  const [trialOpen, setTrialOpen] = useState(false);
  const [trialEmail, setTrialEmail] = useState("");
  const [trialConsent, setTrialConsent] = useState(false);
  const [trialConsentAttempted, setTrialConsentAttempted] = useState(false);
  const [trialState, setTrialState] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [trialMessage, setTrialMessage] = useState("");
  const heroRef = useRef<HTMLElement>(null);
  const pointerTargetRef = useRef({ imageX: 0, imageY: 0, contentX: 0, contentY: 0, tiltX: 0, tiltY: 0, glareX: 0, glareY: 0, glareOpacity: 0 });
  const pointerCurrentRef = useRef({ imageX: 0, imageY: 0, contentX: 0, contentY: 0, tiltX: 0, tiltY: 0, glareX: 0, glareY: 0, glareOpacity: 0 });
  const pointerFrameRef = useRef(0);
  const [reducedMotion, setReducedMotion] = useState(() => {
    try { const stored = window.localStorage.getItem("workflo-reduced-motion"); return stored === "true" || (stored === null && window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch { return false; }
  });
  const trialEmailState = trialEmail.length === 0 ? "idle" : WORK_EMAIL_PATTERN.test(trialEmail.trim()) ? "valid" : "invalid";

  const renderPointerDepth = () => {
    const target = pointerTargetRef.current;
    const current = pointerCurrentRef.current;
    (Object.keys(target) as Array<keyof typeof target>).forEach((key) => { current[key] += (target[key] - current[key]) * 0.105; });
    const hero = heroRef.current;
    if (hero) {
      hero.style.setProperty("--hero-image-x", `${current.imageX.toFixed(2)}px`);
      hero.style.setProperty("--hero-image-y", `${current.imageY.toFixed(2)}px`);
      hero.style.setProperty("--hero-parallax-x", `${current.contentX.toFixed(2)}px`);
      hero.style.setProperty("--hero-parallax-y", `${current.contentY.toFixed(2)}px`);
      hero.style.setProperty("--hero-image-tilt-x", `${current.tiltX.toFixed(2)}deg`);
      hero.style.setProperty("--hero-image-tilt-y", `${current.tiltY.toFixed(2)}deg`);
      hero.style.setProperty("--hero-glare-x", `${current.glareX.toFixed(2)}px`);
      hero.style.setProperty("--hero-glare-y", `${current.glareY.toFixed(2)}px`);
      hero.style.setProperty("--hero-glare-opacity", current.glareOpacity.toFixed(3));
    }
    const distance = Math.max(...(Object.keys(target) as Array<keyof typeof target>).map((key) => Math.abs(target[key] - current[key])));
    pointerFrameRef.current = distance > 0.015 ? window.requestAnimationFrame(renderPointerDepth) : 0;
  };

  const schedulePointerDepth = () => { if (!pointerFrameRef.current) pointerFrameRef.current = window.requestAnimationFrame(renderPointerDepth); };

  const updatePointer = (event: PointerEvent<HTMLElement>) => {
    if (event.pointerType !== "mouse" || reducedMotion || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width * 2 - 1;
    const y = (event.clientY - bounds.top) / bounds.height * 2 - 1;
    const ultrawideTiltFactor = window.matchMedia("(min-width: 1600px) and (min-aspect-ratio: 21/9)").matches ? 0.68 : 1;
    pointerTargetRef.current = { imageX: x * -7, imageY: y * -5, contentX: x * 2.6, contentY: y * 1.8, tiltX: y * -1.5 * ultrawideTiltFactor, tiltY: x * 1.9 * ultrawideTiltFactor, glareX: x * 72, glareY: y * 54, glareOpacity: 0.16 };
    schedulePointerDepth();
  };

  const resetPointer = (immediate = false) => {
    const restingDepth = { imageX: 0, imageY: 0, contentX: 0, contentY: 0, tiltX: 0, tiltY: 0, glareX: 0, glareY: 0, glareOpacity: 0 };
    pointerTargetRef.current = restingDepth;
    if (!immediate) return schedulePointerDepth();
    pointerCurrentRef.current = restingDepth;
    window.cancelAnimationFrame(pointerFrameRef.current);
    pointerFrameRef.current = 0;
    const hero = heroRef.current;
    if (hero) ["--hero-image-x", "--hero-image-y", "--hero-parallax-x", "--hero-parallax-y"].forEach((property) => hero.style.setProperty(property, "0px"));
    if (hero) ["--hero-image-tilt-x", "--hero-image-tilt-y"].forEach((property) => hero.style.setProperty(property, "0deg"));
    if (hero) { hero.style.setProperty("--hero-glare-x", "0px"); hero.style.setProperty("--hero-glare-y", "0px"); hero.style.setProperty("--hero-glare-opacity", "0"); }
  };

  useEffect(() => {
    const hero = heroRef.current;
    if (!hero) return;
    let frame = 0;
    let releaseTimer = 0;
    let targetOffset = 0;
    let currentOffset = 0;

    const render = () => {
      currentOffset += (targetOffset - currentOffset) * 0.14;
      hero.style.setProperty("--hero-scroll-y", `${currentOffset.toFixed(2)}px`);
      if (Math.abs(targetOffset - currentOffset) > 0.1) frame = window.requestAnimationFrame(render);
      else frame = 0;
    };
    const schedule = () => { if (!frame) frame = window.requestAnimationFrame(render); };
    const reset = () => { targetOffset = 0; schedule(); };
    const onScroll = () => {
      if (reducedMotion) return reset();
      targetOffset = Math.max(-18, Math.min(0, -window.scrollY * 0.038));
      schedule();
    };
    const onWheel = (event: WheelEvent) => {
      if (reducedMotion || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return reset();
      targetOffset = Math.max(-18, Math.min(0, targetOffset - event.deltaY * 0.024));
      schedule();
      window.clearTimeout(releaseTimer);
      releaseTimer = window.setTimeout(reset, 720);
    };

    hero.style.setProperty("--hero-scroll-y", "0px");
    window.addEventListener("scroll", onScroll, { passive: true });
    hero.addEventListener("wheel", onWheel, { passive: true });
    onScroll();
    return () => { window.cancelAnimationFrame(frame); window.clearTimeout(releaseTimer); window.removeEventListener("scroll", onScroll); hero.removeEventListener("wheel", onWheel); };
  }, [reducedMotion]);

  useEffect(() => () => window.cancelAnimationFrame(pointerFrameRef.current), []);

  const submitTrial = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (trialState === "submitting") return;
    if (!trialConsent) {
      setTrialConsentAttempted(true);
      return;
    }
    setTrialState("submitting");
    setTrialMessage("");
    try {
      const response = await fetch("/api/trial-signups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: trialEmail, consent: trialConsent }),
      });
      const payload = await response.json().catch(() => ({})) as { ok?: boolean; message?: string };
      if (!response.ok || !payload.ok) throw new Error(payload.message || "Trial requests are temporarily unavailable. Please try again.");
      setTrialState("success");
      setTrialMessage("Your access request is recorded. We’ll be in touch about your trial.");
      setTrialEmail("");
    } catch (error) {
      setTrialState("error");
      setTrialMessage(error instanceof Error ? error.message : "Trial requests are temporarily unavailable. Please try again.");
    }
  };

  const changeTrialDialog = (open: boolean) => {
    setTrialOpen(open);
    if (!open) { setTrialState("idle"); setTrialMessage(""); setTrialConsent(false); setTrialConsentAttempted(false); }
  };

  useEffect(() => { try { window.localStorage.setItem("workflo-reduced-motion", String(reducedMotion)); } catch { /* Preference persistence is optional. */ } }, [reducedMotion]);

  return <main ref={heroRef} className={`minimal-hero ${reducedMotion ? "motion-reduced" : ""}`} onPointerMove={updatePointer} onPointerLeave={() => resetPointer()}>
    <div className="minimal-hero__sandbox-art" aria-hidden="true"><img className="minimal-hero__sandbox-poster" src="/manus-storage/workflo-sandbox-immersive-hero_b63d7110.jpg" alt="" onLoad={() => setHeroImageLoaded(true)} /></div>
    <div className="minimal-hero__scrim" aria-hidden="true" />
    <Link href="/" className={`minimal-hero__brand ${heroImageLoaded ? "is-ready" : ""}`} aria-label="Workflo home"><span>W/</span><strong>WORKFLO</strong></Link>
    <button className={`minimal-hero__motion-toggle ${heroImageLoaded ? "is-ready" : ""}`} type="button" aria-pressed={!reducedMotion} onClick={() => { const next = !reducedMotion; setReducedMotion(next); if (next) resetPointer(true); }}>Motion: {reducedMotion ? "Off" : "On"}</button>
    <span className="minimal-hero__glare" aria-hidden="true" />
    <div className={`minimal-hero__loader ${heroImageLoaded ? "is-complete" : ""}`} aria-live="polite" aria-label="Loading Workflo"><span className="minimal-hero__loader-orbit" aria-hidden="true" /><div><span>LOADING</span></div><i><b style={{ transform: `scaleX(${heroImageLoaded ? 1 : 0.28})` }} /></i></div>
    <div className={`minimal-hero__content ${heroImageLoaded ? "is-ready" : ""}`}>
      <h1><span className="hero-reveal" aria-label={headlineTagline}>{headlineTagline}</span></h1>
      <p>{WORKFLO_HERO.description}</p>
      <div className="minimal-hero__actions"><button className="minimal-hero__primary-action" type="button" onClick={() => setTrialOpen(true)}>Start Free Trial <ArrowUpRight size={17} /></button><Link href="/docs">Documentation <ArrowUpRight size={17} /></Link></div>
    </div>
    <Dialog open={trialOpen} onOpenChange={changeTrialDialog}>
      <DialogContent className="trial-modal" onPointerDownOutside={() => changeTrialDialog(false)} onEscapeKeyDown={() => changeTrialDialog(false)}>
        <DialogHeader>
          <span className="trial-modal__eyebrow">WORKFLO / TRIAL ACCESS</span>
          <DialogTitle>Start your free trial.</DialogTitle>
          <DialogDescription>Use a work email to request access to Workflo’s isolated QA environment.</DialogDescription>
        </DialogHeader>
        {trialState === "success" ? <div className="trial-modal__success" role="status"><div className="trial-modal__success-mark"><CircleCheckBig size={30} /></div><strong>Thank you.</strong><p>{trialMessage}</p><button type="button" onClick={() => changeTrialDialog(false)}>Close</button></div> : <form className="trial-modal__form" onSubmit={submitTrial}><label><span>WORK EMAIL</span><input type="email" name="email" autoComplete="email" placeholder="you@company.com" value={trialEmail} onChange={(event) => setTrialEmail(event.target.value)} required aria-invalid={trialEmailState === "invalid"} aria-describedby="trial-email-feedback" disabled={trialState === "submitting"} /></label><p id="trial-email-feedback" className={`trial-modal__email-feedback is-${trialEmailState}`} aria-live="polite">{trialEmailState === "invalid" ? "Enter a valid work email address." : trialEmailState === "valid" ? "Email format looks good." : ""}</p><div className={`trial-modal__consent ${trialConsentAttempted && !trialConsent ? "is-invalid" : ""}`}><Checkbox id="trial-consent" checked={trialConsent} aria-invalid={trialConsentAttempted && !trialConsent} aria-describedby="trial-consent-error" onCheckedChange={(checked) => { setTrialConsent(checked === true); if (checked) setTrialConsentAttempted(false); }} disabled={trialState === "submitting"} /><label htmlFor="trial-consent">I agree that Workflo may use this email to process my trial request. See the <Link href="/privacy" target="_blank" rel="noreferrer">Privacy Policy</Link>.</label></div>{trialConsentAttempted && !trialConsent && <p id="trial-consent-error" className="trial-modal__consent-error" role="alert">Please confirm consent before requesting a trial.</p>}{trialState === "error" && <p className="trial-modal__error" role="alert">{trialMessage}</p>}<button type="submit" disabled={trialState === "submitting" || trialEmailState !== "valid"}>{trialState === "submitting" ? "Submitting…" : "Request access"}<ArrowUpRight size={16} /></button><small>Your email is used only to process this trial request.</small></form>}
      </DialogContent>
    </Dialog>
  </main>;
}
