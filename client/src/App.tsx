/**
 * Instrument Panel Noir — routing keeps public marketing and dense operational surfaces
 * connected through one compact Workflo control-plane header and shared dark theme.
 */
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import { Route, Switch, useLocation } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import WorkfloHeader from "./components/WorkfloHeader";
import { ThemeProvider } from "./contexts/ThemeContext";
import Dashboard from "./pages/Dashboard";
import Docs from "./pages/Docs";
import Home from "./pages/Home";
import Privacy from "./pages/Privacy";

function Router() {
  const [location] = useLocation();
  const homeRoute = location === "/";
  const consoleRoute = location === "/dashboard";
  return <>
    {!homeRoute && !consoleRoute && <WorkfloHeader />}
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/docs" component={Docs} />
      <Route path="/dashboard" component={Dashboard} />
      <Route path="/privacy" component={Privacy} />
      <Route path="/404" component={NotFound} />
      <Route component={NotFound} />
    </Switch>
  </>;
}

function App() {
  return <ErrorBoundary><ThemeProvider defaultTheme="dark"><TooltipProvider><Toaster richColors theme="dark" position="bottom-right" /><Router /></TooltipProvider></ThemeProvider></ErrorBoundary>;
}

export default App;
