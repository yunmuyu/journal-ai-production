import {loadJournalRules} from '../lib/journal-rules.mjs';

export function verifyExportPadding(spec,report){
 if(spec===null||typeof spec!=='object'||Array.isArray(spec))return false;
 if(spec.policy!==undefined&&(spec.policy===null||typeof spec.policy!=='object'||Array.isArray(spec.policy)))return false;
 if(spec.policy?.diagnostic_only!==undefined&&spec.policy.diagnostic_only!==false)return false;
 const rules=loadJournalRules().normative;
 const margin=Number(rules.margin_pt),dpi=Number(rules.margin_measure_dpi);
 const tolerance=Math.min(Number(rules.margin_measure_tolerance_pt),margin*0.6);
 const declared=spec.policy?.export_crop_padding_pt;
 if(declared!==undefined&&(typeof declared!=='number'||!Number.isFinite(declared)||Math.abs(declared-margin)>1e-9))return false;
 const audit=report?.export_padding_audit;
 if(audit?.rescaled!==false||audit?.measurement_dpi!==dpi||typeof audit?.target_padding_pt!=='number'||Math.abs(audit.target_padding_pt-margin)>1e-9||typeof audit?.tolerance_pt!=='number'||Math.abs(audit.tolerance_pt-tolerance)>1e-9)return false;
 if(!Array.isArray(audit.pages)||audit.pages.length!==1)return false;
 return audit.pages.every(page=>page.rescaled===false&&typeof page.protection_pt==='number'&&Math.abs(page.protection_pt-margin)<=1e-9&&Array.isArray(page.measured_margins_pt)&&page.measured_margins_pt.length===4&&page.measured_margins_pt.every(v=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&Math.abs(v-margin)<=tolerance+1e-9));
}
