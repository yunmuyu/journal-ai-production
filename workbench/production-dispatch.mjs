import {assertProductionRoute,productionInstructions} from './production-route.mjs';

// Dispatch-only boundary: existing candidate verification must not rewrite history.
export function dispatchInstructions(task){
 const route=assertProductionRoute(task),instructions=productionInstructions(route);
 const previousGenerated=[{includeRoutingPolicy:false},{includeProcessingRequirement:false},{includeRoutingPolicy:false,includeProcessingRequirement:false}].map(options=>productionInstructions(route,options));
 if(task.instructions!==undefined&&task.instructions!==instructions&&!previousGenerated.includes(task.instructions))throw Error('制作要求只能由路线合同生成；旧自由文本模板须移出 instructions，原始批注保留在 feedback');
 return instructions;
}
