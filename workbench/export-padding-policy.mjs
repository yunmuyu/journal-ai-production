export function verifyExportPadding(spec,report){
 if(spec===null||typeof spec!=='object'||Array.isArray(spec))return false;
 if(spec.policy!==undefined&&(spec.policy===null||typeof spec.policy!=='object'||Array.isArray(spec.policy)))return false;
 if(spec.policy?.diagnostic_only!==undefined&&spec.policy.diagnostic_only!==false)return false;
 const target=spec?.policy?.export_crop_padding_pt===undefined?0.25:spec.policy.export_crop_padding_pt,audit=report?.export_padding_audit;
 if(typeof target!=='number'||!Number.isFinite(target)||target<0||target>12)return false;
 if(audit?.rescaled!==false||audit?.measurement_dpi!==1200||audit?.target_padding_pt!==target||audit?.tolerance_pt!==0.065)return false;
 if(!Array.isArray(audit.pages)||audit.pages.length!==1)return false;
 return audit.pages.every(page=>page.rescaled===false&&page.protection_pt===target&&Array.isArray(page.measured_margins_pt)&&page.measured_margins_pt.length===4&&page.measured_margins_pt.every(v=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&Math.abs(v-target)<=0.065));
}
