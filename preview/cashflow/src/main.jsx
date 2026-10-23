import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { CashCommandCenterView } from "../../../frontend/src/components/cfo/CashCommandCenter.jsx";
import scenarios from "../data/scenarios.json";

function startingScenario() {
  const id = window.location.hash.slice(1);
  return scenarios.some((scenario) => scenario.id === id) ? id : scenarios[0].id;
}

function Preview() {
  const [scenarioId, setScenarioId] = useState(startingScenario);
  const scenario = scenarios.find((item) => item.id === scenarioId);

  const selectScenario = (id) => {
    setScenarioId(id);
    window.history.replaceState(null, "", `#${id}`);
  };

  return (
    <main className="preview-shell">
      <header className="preview-header">
        <div className="preview-brand">Panorama Pilot <span>2</span></div>
        <div className="preview-label" data-testid="preview-data-label"><span aria-hidden="true" />Anteprima · dati di prova</div>
      </header>

      <section className="preview-intro" aria-labelledby="preview-title">
        <div className="preview-eyebrow">Modulo cassa</div>
        <h1 id="preview-title">Verifica previsioni di cassa</h1>
        <p>Confronta quattro situazioni nel modulo cassa. I dati sono sintetici; i risultati sono calcolati dal motore del progetto.</p>
      </section>

      <section className="preview-scenarios" aria-labelledby="scenarios-title">
        <h2 id="scenarios-title">Scegli uno scenario</h2>
        <div className="preview-scenario-grid" role="group" aria-label="Scenari di verifica">
          {scenarios.map((item, index) => (
            <button
              key={item.id}
              type="button"
              className={`preview-scenario${item.id === scenario.id ? " is-active" : ""}`}
              aria-pressed={item.id === scenario.id}
              onClick={() => selectScenario(item.id)}
              data-testid={`preview-scenario-${item.id}`}
            >
              <span className="preview-scenario-number" aria-hidden="true">0{index + 1}</span>
              <span>{item.title}</span>
              <span className="preview-scenario-check" aria-hidden="true">{item.id === scenario.id ? "✓" : ""}</span>
            </button>
          ))}
        </div>
        <p className="preview-description" aria-live="polite" data-testid="preview-scenario-description">{scenario.description}</p>
      </section>

      <section className="preview-dashboard" aria-label={`Modulo cassa: ${scenario.title}`} data-testid="preview-dashboard">
        <CashCommandCenterView key={scenario.id} data={scenario.data} />
      </section>

      <footer className="preview-footer">
        <span>Panorama Pilot · Verifica del solo modulo cassa</span>
        <span>Dati di prova · Interfaccia del progetto</span>
      </footer>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<Preview />);
