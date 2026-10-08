/**
 * Instrument Panel Noir — persistent navigation is a compact control-plane rail:
 * graphite surface, sharp dividers, Space Grotesk labels, and a single mint action.
 */
import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { ArrowUpRight, Menu, X } from "lucide-react";

const markUrl = "/manus-storage/workflo-mark_cdba888e.png";

export default function WorkfloHeader() {
  const [location] = useLocation();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const navItems = [
    { href: "/#protocol", label: "Protocol", exact: false },
    { href: "/#receipts", label: "Receipts", exact: false },
    { href: "/docs", label: "Docs", exact: true },
    { href: "/dashboard", label: "Console", exact: true },
  ];

  return (
    <header className={`site-header ${scrolled ? "site-header--scrolled" : ""}`}>
      <div className="header-inner">
        <Link href="/" className="brand-lockup" aria-label="Workflo home">
          <img className="brand-mark" src={markUrl} alt="" />
          <span>workflo</span>
        </Link>

        <nav className="desktop-nav" aria-label="Main navigation">
          {navItems.map((item) => {
            const active = item.exact && location === item.href;
            return item.href.includes("#") ? (
              <a key={item.label} href={item.href} className="nav-link">{item.label}</a>
            ) : (
              <Link key={item.label} href={item.href} className={`nav-link ${active ? "nav-link--active" : ""}`}>{item.label}</Link>
            );
          })}
        </nav>

        <div className="header-actions">
          <Link href="/dashboard" className="button button--small button--signal">
            Open console <ArrowUpRight size={15} aria-hidden="true" />
          </Link>
          <button className="mobile-menu-button" onClick={() => setOpen(!open)} aria-label="Toggle navigation" aria-expanded={open}>
            {open ? <X size={19} /> : <Menu size={19} />}
          </button>
        </div>
      </div>

      {open && (
        <div className="mobile-nav">
          {navItems.map((item) => item.href.includes("#") ? (
            <a key={item.label} href={item.href} onClick={() => setOpen(false)}>{item.label}</a>
          ) : (
            <Link key={item.label} href={item.href} onClick={() => setOpen(false)}>{item.label}</Link>
          ))}
        </div>
      )}
    </header>
  );
}

