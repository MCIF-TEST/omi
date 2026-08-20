/**
 * When the product opens.
 *
 * Copy only. The switch that actually opens the site is `OMI_LOCKDOWN` on the API service, and it
 * is deliberately NOT a date: a gate that lifts itself on a timezone boundary would open the
 * product while nobody was watching, and a date that slips would leave the page advertising one
 * that has already passed while the site stayed shut. A human flips the switch; this string is what
 * the page promises in the meantime.
 *
 * Moving the date is an env var edit and a redeploy of the web service, with no code change.
 */
export const LAUNCH_DATE_LABEL =
  process.env.NEXT_PUBLIC_LAUNCH_DATE || 'September 20';


/**
 * Whether the product is locked, as the WEB service sees it.
 *
 * A second copy of `OMI_LOCKDOWN`, and deliberately so. The landing page makes no API call by
 * design (see app/page.tsx: putting FastAPI in the critical path of the one page traffic is bought
 * for capped its throughput at the API's and took marketing down with it), so it cannot ask the
 * server what mode it is in. The only alternatives were a blocking fetch on the front page or a
 * client round trip, and both are worse than one mirrored value.
 *
 * The mirror is safe because it is the SAME pattern the trial credits already use: both values are
 * committed side by side in render.yaml and reconciled by
 * `tests/test_deployed_credit_contract.py`, which fails if they disagree.
 *
 * IT IS NOT THE CONTROL. The API refuses the demo on its own (app/routes/scan_async.py), so if this
 * value were ever stale the worst case is a form that renders and then reports the product is not
 * open — not a scan that actually runs.
 */
export const LOCKED = process.env.NEXT_PUBLIC_LOCKDOWN === 'true';
