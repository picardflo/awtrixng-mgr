/**
 * Takes the wiki screenshots against the demo environment.
 *
 * Never run this against your own installation: the shots have to be
 * identical from one run to the next, which only holds with the fixed data
 * `scripts/demo/serve.py` sets up — and a reconciler pointed at a display in
 * service deletes the apps it does not know.
 *
 *   node capture.mjs --base http://127.0.0.1:9000 --out ../../docs/screenshots
 *
 * Shots are full-page on purpose. Cropping to a card looked tidier but tied
 * every screenshot to a CSS class, and this script is meant to still work in
 * a year.
 */

import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((pairs, value, index, all) => {
    if (value.startsWith("--")) pairs.push([value.slice(2), all[index + 1]]);
    return pairs;
  }, []),
);

const BASE = args.base ?? "http://127.0.0.1:9000";
const OUT = args.out ?? "docs/screenshots";
const ONLY = args.only ? new RegExp(args.only) : null;
/** "login" needs the demo started with --password, so it is a separate pass
 *  rather than a step in the middle of the others. */
const SCENARIO = args.scenario ?? "main";
const VIEWPORT = { width: 1280, height: 900 };

const taken = [];
const missed = [];

async function shot(page, name) {
  if (ONLY && !ONLY.test(name)) return;
  await page.waitForTimeout(400); // let transitions settle
  await page.addStyleTag({ content: UNSTICK });
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
  taken.push(name);
  console.log(`  ✓ ${name}`);
}

async function go(page, route) {
  await page.goto(`${BASE}/#/${route}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
}

/** Clicks, and says plainly which label went missing rather than dying on a
 *  timeout thirty seconds later. */
async function click(page, name, { optional = false } = {}) {
  const target = page.getByRole("button", { name }).first();
  try {
    await target.waitFor({ state: "visible", timeout: 5000 });
    await target.click();
    await page.waitForTimeout(800);
    return true;
  } catch {
    const label = String(name);
    if (!optional) missed.push(label);
    console.log(`  ⚠ button not found: ${label}`);
    return false;
  }
}

/** Some things are cards, not buttons — adding a service is done by picking
 *  one from the list of what is available. */
async function clickText(page, text) {
  const target = page.getByText(text, { exact: true }).first();
  try {
    await target.waitFor({ state: "visible", timeout: 5000 });
    await target.click();
    await page.waitForTimeout(800);
    return true;
  } catch {
    missed.push(String(text));
    console.log(`  ⚠ text not found: ${text}`);
    return false;
  }
}

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: VIEWPORT,
  // 1, not 2. At 2 every capture weighed 5 MB a round, and the version
  // number printed in the header means *every* capture changes on *every*
  // bump — the repository had reached 98 MB of dead screenshots against
  // 5.5 MB of everything else. A 1280-wide shot of a 1280-wide viewport is
  // pixel-exact at normal zoom, which is how a wiki page shows it.
  deviceScaleFactor: 1,
  locale: "fr-FR",
});
// The manual is in French, so the screenshots are too.
await context.addInitScript(() =>
  window.localStorage.setItem("awtrixng-mgr.locale", "fr"),
);

/** A full-page screenshot renders a sticky header wherever the page happens
 *  to be scrolled, so it lands in the middle of the form. Pinning everything
 *  to the flow puts it back at the top, where a reader expects it. */
const UNSTICK = `
  header, [class*="sticky"], [class*="fixed"] {
    position: static !important;
  }
`;

const page = await context.newPage();
await mkdir(OUT, { recursive: true });

if (SCENARIO === "login") {
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await shot(page, "connexion");
  await browser.close();
  console.log(`\n${taken.length} capture(s) dans ${OUT}`);
  process.exit(missed.length ? 1 : 0);
}

// -- Dashboard --------------------------------------------------------------
await go(page, "dashboard");
await shot(page, "dashboard");

// -- Displays ---------------------------------------------------------------
await go(page, "devices");
await shot(page, "devices-liste");

await click(page, /Tester la connexion/i);
await page.waitForTimeout(800);
await shot(page, "device-test");

// The built-in apps panel is gone: measured on NG 1.1.2, there is no way to
// disable them at all. `DELETE /api/v1/apps/Battery` answers {"ok": true} and
// changes nothing, and none of the 42 settings governs them.

// The clock's own settings — brightness, buzzer volume, rotation, formats.
// None of this is reachable from the AWTRIX web interface.
await click(page, /Réglages de l'horloge/i);
await page.waitForTimeout(900);
await shot(page, "device-reglages");
await click(page, /Réglages de l'horloge/i, { optional: true });

// Quiet hours: the half of the old bedroom mode a light sensor cannot do.
// The dimming moved into the clock's own settings — `minBrightness` reads the
// room rather than the hour.
await click(page, /Heures calmes/i);
await page.waitForTimeout(900);
await shot(page, "device-heures-calmes");
await click(page, /Heures calmes/i, { optional: true });

await click(page, /Ajouter un AWTRIX/i);
await shot(page, "device-ajout");

// -- Services ---------------------------------------------------------------
await go(page, "connectors");
await shot(page, "services-liste");

// The fuel service first, because its form is the one that shows the fuel
// checkboxes. Before the weather one, not after: `go()` keeps the same hash,
// so the SPA would still be sitting on the form it had just opened.
await clickText(page, "Prix des carburants");
await shot(page, "service-carburants");

await go(page, "connectors");
await page.reload({ waitUntil: "networkidle" });
await clickText(page, "Météo");
await shot(page, "service-ajout");

// The saved fuel service, whose form lists the nearby stations. Only an
// existing service can: the list comes from its own place and radius.
await go(page, "connectors");
await page.reload({ waitUntil: "networkidle" });
const carburants = page
  .getByRole("heading", { name: "Carburants", exact: true })
  .locator("xpath=ancestor::div[contains(@class,'rounded-xl')][1]");
try {
  await carburants.getByRole("button", { name: /^Modifier$/ }).click({ timeout: 5000 });
  // The station list is fetched from the service, so it arrives after the form.
  await page.waitForTimeout(1500);
  await shot(page, "service-carburants-stations");
} catch {
  missed.push("service Carburants");
  console.log("  ⚠ service Carburants introuvable dans la liste");
}

// -- Widgets ----------------------------------------------------------------
await go(page, "widgets");
await shot(page, "widgets-liste");

await click(page, /^Modifier$/i);
await page.waitForTimeout(1000);
// Unfolded: the page documents these options, and one of them greys itself
// out depending on the widget — which a collapsed section cannot show.
await click(page, /Avancé/);
await page.waitForTimeout(500);
await shot(page, "widget-edition");

// The moon widget, opened by name rather than by position: the list grows and
// "the first card" would quietly become a different widget.
await go(page, "widgets");
// From the heading up to the card that holds it — filtering a bare "div" by
// content matched a wrapper without the buttons.
const lune = page
  .getByRole("heading", { name: "Lune", exact: true })
  .locator("xpath=ancestor::div[contains(@class,'rounded-xl')][1]");
try {
  await lune.getByRole("button", { name: /^Modifier$/ }).click({ timeout: 5000 });
  await page.waitForTimeout(1200);
  await shot(page, "widget-lune");
} catch {
  missed.push("widget Lune");
  console.log("  ⚠ widget Lune introuvable dans la liste");
}

// The sun widget, for its colours: the text and the bar both follow the
// connector here, and a screenshot is the only thing that shows they match.
await go(page, "widgets");
const soleil = page
  .getByRole("heading", { name: "Soleil", exact: true })
  .locator("xpath=ancestor::div[contains(@class,'rounded-xl')][1]");
try {
  await soleil.getByRole("button", { name: /^Modifier$/ }).click({ timeout: 5000 });
  await page.waitForTimeout(1200);
  await shot(page, "widget-soleil");
} catch {
  missed.push("widget Soleil");
  console.log("  ⚠ widget Soleil introuvable dans la liste");
}

// -- Reminders --------------------------------------------------------------
await go(page, "reminders");
await shot(page, "rappels");

await click(page, /^Modifier$/);
await page.waitForTimeout(1000);
// Unfolded, like the widget builder's: since 0.13.0 the block is the same
// component in both forms, and a collapsed section documents neither.
await click(page, /Avancé/);
await page.waitForTimeout(500);
await shot(page, "rappel-edition");

// Duplicating opens the form on a copy and creates nothing: the list below
// still holds the original alone, which is the point of the shot.
await go(page, "reminders");
await page.reload({ waitUntil: "networkidle" });
await click(page, /^Dupliquer$/);
await page.waitForTimeout(900);
await shot(page, "rappel-duplication");

// -- Backup -----------------------------------------------------------------
await go(page, "backup");
await shot(page, "sauvegarde");

await browser.close();

console.log(`\n${taken.length} capture(s) dans ${OUT}`);
if (missed.length) {
  console.error(`\n${missed.length} bouton(s) introuvable(s) : ${missed.join(", ")}`);
  console.error("L'interface a probablement changé — corrigez capture.mjs.");
  process.exit(1);
}
