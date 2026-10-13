#!/usr/bin/env node

const fs = require("fs");

const PORTS = { top: true, right: true, bottom: true, left: true };
const PORT_POSITIONS = { center: true, upper: true, lower: true, left: true, right: true };
const LABEL_POSITIONS = { source: true, middle: true, target: true };
const LABEL_SIDES = { above: true, below: true, left: true, right: true };
const ARROWS = { none: true, start: true, end: true, both: true };
const LINE_STYLES = { solid: true, dashed: true, dotted: true };
const ROUTE_STYLES = { straight: true, orthogonal: true, curve: true };
const SHAPES = { terminator: true, process: true, decision: true, ellipse: true, cylinder: true, arrow: true, brace: true, plusCircle: true, minusCircle: true, label: true, functionBlock: true, multiplier: true, summer: true, port: true, waveBlock: true, sideCurveBlock: true, inputOutput: true, predefinedProcess: true };

function fail(message) {
  throw new Error(message);
}

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function textUnits(text) {
  let units = 0;
  for (const char of text) units += char.codePointAt(0) <= 255 ? 0.5 : 1;
  return units;
}

function validId(value) {
  return /^[A-Za-z][A-Za-z0-9_-]*$/.test(value || "");
}

function positiveInteger(value) {
  return finiteNumber(value) && value >= 1 && Math.floor(value) === value;
}

function gridAxis(value) {
  return ["from", "to", "from+gap", "from-gap", "to+gap", "to-gap"].includes(value) ||
    (finiteNumber(value) && Math.round(value * 2) === value * 2);
}

function keepsSourceAxis(point) {
  return ["from", "from+gap", "from-gap"].includes(point.x) || ["from", "from+gap", "from-gap"].includes(point.y);
}

function keepsTargetAxis(point) {
  return ["to", "to+gap", "to-gap"].includes(point.x) || ["to", "to+gap", "to-gap"].includes(point.y);
}

function expectedSourceGap(port) {
  return {
    left: ["x", "from-gap"],
    right: ["x", "from+gap"],
    top: ["y", "from+gap"],
    bottom: ["y", "from-gap"]
  }[port];
}

function expectedTargetGap(port) {
  return {
    left: ["x", "to-gap"],
    right: ["x", "to+gap"],
    top: ["y", "to+gap"],
    bottom: ["y", "to-gap"]
  }[port];
}

function validateGapDirection(point, expected, prefix, edgeIndex) {
  const axis = expected[0];
  const value = point[axis];
  if (typeof value === "string" && value.startsWith(prefix) && value.endsWith("gap") && value !== expected[1]) {
    fail(`连接 ${edgeIndex + 1} 的 ${axis}:${value} 朝节点内侧；${expected[1]} 才是该端口的外侧 3 mm 方向。`);
  }
}

function validateNode(node, index, ids, version, rootKind) {
  if (!node || typeof node !== "object" || Array.isArray(node)) fail(`节点 ${index + 1} 必须是对象。`);
  if (!validId(node.id)) fail(`节点 ${index + 1} 的 id 无效。`);
  if (ids[node.id]) fail(`节点 id 重复：${node.id}`);
  if (typeof node.text !== "string" || (node.text.length === 0 && !["multiplier", "summer", "port", "arrow", "brace", "plusCircle", "minusCircle"].includes(node.shape))) fail(`节点 ${node.id} 缺少 text。`);
  if (!SHAPES[node.shape]) fail(`节点 ${node.id} 的 shape 无效。`);
  if (["functionBlock", "multiplier", "summer", "port"].includes(node.shape) && (version < 3 || rootKind !== "signalFlow")) fail(`节点 ${node.id} 的 signalFlow 专用 shape 需要 schemaVersion 3 的 signalFlow。`);
  if (node.shape === "label" && (version < 3 || rootKind !== "blockDiagram")) fail(`节点 ${node.id} 的 label shape 需要 schemaVersion 3 的 blockDiagram。`);
  if (!finiteNumber(node.row) || node.row < 0 || Math.floor(node.row) !== node.row) fail(`节点 ${node.id} 的 row 必须是非负整数。`);
  if (!finiteNumber(node.column) || node.column < 0 || Math.round(node.column * 2) !== node.column * 2) fail(`节点 ${node.id} 的 column 必须是非负整数或半整数。`);
  if (node.textDirection !== undefined && node.textDirection !== "horizontal" && node.textDirection !== "vertical") fail(`节点 ${node.id} 的 textDirection 无效。`);
  if (node.arrowDirection !== undefined && !["right", "left", "up", "down"].includes(node.arrowDirection)) fail(`节点 ${node.id} 的 arrowDirection 无效。`);
  if (node.arrowHeads !== undefined && !["end", "both"].includes(node.arrowHeads)) fail(`节点 ${node.id} 的 arrowHeads 无效。`);
  if ((node.arrowDirection !== undefined || node.arrowHeads !== undefined) && node.shape !== "arrow") fail(`节点 ${node.id} 的 arrowDirection/arrowHeads 只适用于 arrow。`);
  if (node.braceSide !== undefined && !["left", "right", "top", "bottom"].includes(node.braceSide)) fail(`节点 ${node.id} 的 braceSide 无效。`);
  if (node.braceSide !== undefined && node.shape !== "brace") fail(`节点 ${node.id} 的 braceSide 只适用于 brace。`);
  if (node.heightGroup !== undefined && !validId(node.heightGroup)) fail(`节点 ${node.id} 的 heightGroup 无效。`);
  if (node.widthGroup !== undefined && !validId(node.widthGroup)) fail(`节点 ${node.id} 的 widthGroup 无效。`);
  if (node.rowSpan !== undefined && !positiveInteger(node.rowSpan)) fail(`节点 ${node.id} 的 rowSpan 必须是正整数。`);
  if (node.columnSpan !== undefined && !positiveInteger(node.columnSpan)) fail(`节点 ${node.id} 的 columnSpan 必须是正整数。`);
  if ((node.rowSpan > 1 || node.columnSpan > 1) && Math.floor(node.column) !== node.column) fail(`跨行或跨列节点 ${node.id} 必须使用整数 column。`);
  if (version < 3 && (node.heightGroup !== undefined || node.widthGroup !== undefined || node.rowSpan !== undefined || node.columnSpan !== undefined || node.braceSide !== undefined || node.arrowDirection !== undefined || node.arrowHeads !== undefined || node.shape === "ellipse" || node.shape === "cylinder" || node.shape === "arrow" || node.shape === "brace" || node.shape === "plusCircle" || node.shape === "minusCircle" || node.shape === "label" || node.shape === "functionBlock" || node.shape === "multiplier" || node.shape === "summer" || node.shape === "port" || node.shape === "waveBlock" || node.shape === "sideCurveBlock" || node.shape === "inputOutput" || node.shape === "predefinedProcess")) fail(`节点 ${node.id} 使用了 schemaVersion 3 字段。`);
  if (node.shape === "decision") {
    const lines = node.text.replace(/\r\n|\r/g, "\n").split("\n");
    const longest = Math.max(...lines.map(textUnits));
    if (longest > 14) fail(`[decision-line] 判断节点 ${node.id} 的单行文字过长；请按原图或自然短语换行，避免超扁菱形。`);
  }
  ids[node.id] = true;
}

function validateEdge(edge, index, ids, edgeIds, version, kind) {
  if (!edge || typeof edge !== "object" || Array.isArray(edge)) fail(`连接 ${index + 1} 必须是对象。`);
  const hasFrom = edge.from !== undefined;
  const hasFromEdge = edge.fromEdge !== undefined;
  const hasTo = edge.to !== undefined;
  const hasToEdge = edge.toEdge !== undefined;
  if (hasFrom === hasFromEdge || hasTo === hasToEdge || (hasFrom && !ids[edge.from]) || (hasTo && !ids[edge.to])) fail(`连接 ${index + 1} 的起点和终点必须各自使用一个节点/容器或一条已命名连接。`);
  if (hasFromEdge && (edgeIds[edge.fromEdge] === undefined || edgeIds[edge.fromEdge] >= index || edge.fromEdgePosition !== "middle")) fail(`连接 ${index + 1} 的 fromEdge 必须引用它之前的已命名连接，且 fromEdgePosition 必须为 middle。`);
  if (!hasFromEdge && edge.fromEdgePosition !== undefined) fail(`连接 ${index + 1} 只有使用 fromEdge 时才能设置 fromEdgePosition。`);
  if (hasToEdge && (edgeIds[edge.toEdge] === undefined || edgeIds[edge.toEdge] >= index || edge.toEdgePosition !== "middle")) fail(`连接 ${index + 1} 的 toEdge 必须引用它之前的已命名连接，且 toEdgePosition 必须为 middle。`);
  if (!hasToEdge && edge.toEdgePosition !== undefined) fail(`连接 ${index + 1} 只有使用 toEdge 时才能设置 toEdgePosition。`);
  if (hasFrom && hasTo && edge.from === edge.to) fail(`不支持节点自连：${edge.from}`);
  if (edge.label !== undefined && typeof edge.label !== "string") fail(`连接 ${index + 1} 的 label 必须是字符串。`);
  const hasFromPort = edge.fromPort !== undefined;
  const hasToPort = edge.toPort !== undefined;
  if (hasFromPort !== hasToPort) fail(`连接 ${index + 1} 必须同时设置 fromPort 和 toPort。`);
  if (hasFromPort && (!PORTS[edge.fromPort] || !PORTS[edge.toPort])) fail(`连接 ${index + 1} 的端口无效。`);
  if (edge.fromPortPosition !== undefined && (!hasFromPort || !PORT_POSITIONS[edge.fromPortPosition])) fail(`连接 ${index + 1} 的 fromPortPosition 无效。`);
  if (edge.toPortPosition !== undefined && (!hasToPort || !PORT_POSITIONS[edge.toPortPosition])) fail(`连接 ${index + 1} 的 toPortPosition 无效。`);
  if (edge.labelPosition !== undefined && !LABEL_POSITIONS[edge.labelPosition]) fail(`连接 ${index + 1} 的 labelPosition 无效。`);
  if (edge.arrow !== undefined && !ARROWS[edge.arrow]) fail(`连接 ${index + 1} 的 arrow 无效。`);
  if (edge.via !== undefined) {
    if (!Array.isArray(edge.via) || edge.via.length === 0) fail(`连接 ${index + 1} 的 via 必须是非空数组。`);
    if (!hasFromPort) fail(`连接 ${index + 1} 使用 via 时必须显式设置端口。`);
    if (edge.fromPort === edge.toPort) fail(`[route-reversal] 连接 ${index + 1} 的同侧回路不能使用 via；请改用 routeLane，避免 3 mm 局部腿反向折返。`);
    edge.via.forEach((point, pointIndex) => {
      if (!point || typeof point !== "object" || Array.isArray(point) || !gridAxis(point.x) || !gridAxis(point.y)) {
        fail(`连接 ${index + 1} 的 via[${pointIndex}] 坐标无效。`);
      }
    });
    if (!keepsSourceAxis(edge.via[0])) fail(`连接 ${index + 1} 的首个 via 必须保留 from 坐标轴，避免起始段产生斜线。`);
    if (!keepsTargetAxis(edge.via[edge.via.length - 1])) fail(`连接 ${index + 1} 的最后 via 必须保留 to 坐标轴，避免末段产生斜线。`);
    validateGapDirection(edge.via[0], expectedSourceGap(edge.fromPort), "from", index);
    validateGapDirection(edge.via[edge.via.length - 1], expectedTargetGap(edge.toPort), "to", index);
  }
  if (edge.labelSegment !== undefined && (!finiteNumber(edge.labelSegment) || edge.labelSegment < 0 || Math.floor(edge.labelSegment) !== edge.labelSegment)) fail(`连接 ${index + 1} 的 labelSegment 必须是非负整数。`);
  if (edge.labelSide !== undefined && !LABEL_SIDES[edge.labelSide]) fail(`连接 ${index + 1} 的 labelSide 无效。`);
  if (edge.lineStyle !== undefined && !LINE_STYLES[edge.lineStyle]) fail(`连接 ${index + 1} 的 lineStyle 无效。`);
  if (edge.routeStyle !== undefined && !ROUTE_STYLES[edge.routeStyle]) fail(`连接 ${index + 1} 的 routeStyle 无效。`);
  if (edge.shaftLength !== undefined && edge.shaftLength !== "2mm" && edge.shaftLength !== "3mm") fail(`连接 ${index + 1} 的 shaftLength 无效。`);
  if (edge.routeLane !== undefined && !positiveInteger(edge.routeLane)) fail(`连接 ${index + 1} 的 routeLane 必须是正整数。`);
  if (edge.routeLane !== undefined && (!hasFromPort || edge.fromPort !== edge.toPort || edge.via !== undefined)) fail(`连接 ${index + 1} 的 routeLane 只能用于无 via 的同侧端口回路。`);
  if(edge.routeStyle==='curve' && (edge.fromPort!==edge.toPort || !['top','bottom'].includes(edge.fromPort) || edge.via || (edge.arrow && !['none','end'].includes(edge.arrow)))) fail('Curve requires matching top/bottom ports and end/none arrow');
  if (edge.routeStyle === "straight" && kind !== "blockDiagram" && kind !== "signalFlow") fail(`连接 ${index + 1} 只有 blockDiagram 或 signalFlow 可以使用 straight 路线。`);
  if (edge.routeStyle === "straight" && !hasFromPort) fail(`连接 ${index + 1} 使用 straight 时必须显式设置端口。`);
  if (edge.routeStyle === "straight" && edge.via !== undefined) fail(`连接 ${index + 1} 不能同时使用 straight 和 via。`);
  if ((hasFromEdge || hasToEdge) && (edge.routeStyle === "straight" || edge.via !== undefined)) fail(`连接 ${index + 1} 与其他连接衔接时只能使用自动正交路线。`);
  if (version === 1 && (hasFromPort || edge.labelPosition !== undefined)) fail(`连接 ${index + 1} 使用了 schemaVersion 2 字段。`);
  if (version < 3 && (edge.id !== undefined || edge.fromEdge !== undefined || edge.fromEdgePosition !== undefined || edge.toEdge !== undefined || edge.toEdgePosition !== undefined || edge.arrow !== undefined || edge.via !== undefined || edge.labelSegment !== undefined || edge.labelSide !== undefined || edge.lineStyle !== undefined || edge.routeStyle !== undefined || edge.fromPortPosition !== undefined || edge.toPortPosition !== undefined || edge.shaftLength !== undefined || edge.routeLane !== undefined)) fail(`连接 ${index + 1} 使用了 schemaVersion 3 字段。`);
}

function validateContainers(containers, ids, endpointIds, version, nodes) {
  if (containers === undefined) return;
  if (version < 3) fail("containers 需要 schemaVersion 3。");
  if (!Array.isArray(containers)) fail("containers 必须是数组。");
  const seen = Object.create(null);
  const rowById = Object.fromEntries((nodes || []).map((node) => [node.id, node.row]));
  containers.forEach((container, index) => {
    if (!container || typeof container !== "object" || Array.isArray(container) || !validId(container.id)) fail(`容器 ${index + 1} 的 id 无效。`);
    if (seen[container.id] || ids[container.id]) fail(`容器 id 重复或与节点冲突：${container.id}`);
    if (!Array.isArray(container.members) || container.members.length === 0) fail(`容器 ${container.id} 的 members 必须是非空数组。`);
    if (container.padding !== undefined && container.padding !== "minimal" && container.padding !== "tight" && container.padding !== "normal") fail(`容器 ${container.id} 的 padding 无效。`);
    if (container.sizeClass !== undefined && container.sizeClass !== "wideNested") fail(`容器 ${container.id} 的 sizeClass 无效。`);
    if (container.sizeClass === "wideNested" && container.members.length !== 1) fail(`wideNested 容器必须只有一个成员。`);
    if (container.lineStyle !== undefined && !LINE_STYLES[container.lineStyle]) fail(`容器 ${container.id} 的 lineStyle 无效。`);
    if (container.cornerStyle !== undefined && container.cornerStyle !== "square" && container.cornerStyle !== "rounded") fail(`容器 ${container.id} 的 cornerStyle 无效。`);
    if (container.label !== undefined && (typeof container.label !== "string" || container.label.length === 0)) fail(`容器 ${container.id} 的 label 无效。`);
    if (container.labelPosition !== undefined && container.labelPosition !== "topCenter" && container.labelPosition !== "bottomRight") fail(`容器 ${container.id} 的 labelPosition 无效。`);
    if (container.frameGroup !== undefined && !validId(container.frameGroup)) fail(`容器 ${container.id} 的 frameGroup 无效。`);
    if (container.memberDistribution !== undefined && container.memberDistribution !== "spaceBetween" && container.memberDistribution !== "compact") fail(`容器 ${container.id} 的 memberDistribution 无效。`);
    if (container.memberDistribution === "spaceBetween" || container.memberDistribution === "compact") {
      const rows = new Set(container.members.map((member) => rowById[member]));
      if (rows.size > 1) fail(`[member-distribution-row] 容器 ${container.id} 的 spaceBetween 只能用于同一 row 的单行成员；多行模块或设备+说明组合必须省略该字段。`);
    }
    for (const member of container.members) if (!ids[member]) fail(`容器 ${container.id} 引用了不存在的节点：${member}`);
    seen[container.id] = true;
    endpointIds[container.id] = true;
  });
}

function validateSwimlaneLayout(root, ids) {
  if (root.swimlaneLayout === undefined) return;
  if (root.swimlaneLayout !== "vertical" && root.swimlaneLayout !== "horizontal") fail("swimlaneLayout 只能是 vertical 或 horizontal。");
  if (root.schemaVersion < 3 || root.kind !== "flowchart") fail("swimlaneLayout 需要 schemaVersion 3 的 flowchart。");
  if (!Array.isArray(root.containers) || root.containers.length < 2) fail("[swimlane-count] 共享泳道至少需要两个 containers。");
  const owners = Object.create(null);
  let style;
  root.containers.forEach((lane) => {
    style = style || lane.lineStyle || "solid";
    if ((lane.lineStyle || "solid") !== style) fail("[swimlane-frame] 共享泳道的 lineStyle 必须一致。");
    if (typeof lane.label !== "string" || lane.label.length === 0) fail(`[swimlane-title] 泳道 ${lane.id} 必须有非空 label。`);
    if (lane.labelDirection !== undefined && lane.labelDirection !== "horizontal" && lane.labelDirection !== "vertical") fail(`[swimlane-title] 泳道 ${lane.id} 的 labelDirection 无效。`);
    if (lane.cornerStyle !== undefined && lane.cornerStyle !== "square") fail(`[swimlane-frame] 泳道 ${lane.id} 必须使用直角边框。`);
    if (lane.memberDistribution !== undefined || lane.frameGroup !== undefined || lane.labelPosition !== undefined) fail(`[swimlane-frame] 泳道 ${lane.id} 不能使用普通容器的分布、框组或标题位置。`);
    for (const member of lane.members) {
      if (!ids[member]) continue;
      if (owners[member]) fail(`[swimlane-member] 节点 ${member} 不能同时属于泳道 ${owners[member]} 和 ${lane.id}。`);
      owners[member] = lane.id;
    }
  });
  for (const id of Object.keys(ids)) if (!owners[id]) fail(`[swimlane-member] 节点 ${id} 未归属任何泳道。`);
}

function validateStacks(stacks, ids, version) {
  if (stacks === undefined) return;
  if (version < 3) fail("stacks 需要 schemaVersion 3。");
  if (!Array.isArray(stacks)) fail("stacks 必须是数组。");
  const seenIds = Object.create(null);
  const seenMembers = Object.create(null);
  stacks.forEach((stack, index) => {
    if (!stack || typeof stack !== "object" || Array.isArray(stack) || !validId(stack.id)) fail(`纵向栈 ${index + 1} 的 id 无效。`);
    if (seenIds[stack.id]) fail(`纵向栈 id 重复：${stack.id}`);
    if (!Array.isArray(stack.members) || stack.members.length < 2) fail(`纵向栈 ${stack.id} 至少需要两个成员。`);
    if (stack.gap !== undefined && stack.gap !== "minimal" && stack.gap !== "standard") fail(`纵向栈 ${stack.id} 的 gap 无效。`);
    for (const member of stack.members) {
      if (!ids[member]) fail(`纵向栈 ${stack.id} 引用了不存在的节点：${member}`);
      if (seenMembers[member]) fail(`节点 ${member} 不能同时属于多个纵向栈。`);
      seenMembers[member] = true;
    }
    seenIds[stack.id] = true;
  });
}

function validateHorizontalStacks(stacks, ids, version) {
  if (stacks === undefined) return;
  if (version < 3) fail("horizontalStacks 需要 schemaVersion 3。");
  if (!Array.isArray(stacks)) fail("horizontalStacks 必须是数组。");
  const seenIds = Object.create(null);
  const seenMembers = Object.create(null);
  stacks.forEach((stack, index) => {
    if (!stack || typeof stack !== "object" || Array.isArray(stack) || !validId(stack.id)) fail(`水平栈 ${index + 1} 的 id 无效。`);
    if (seenIds[stack.id]) fail(`水平栈 id 重复：${stack.id}`);
    if (!Array.isArray(stack.members) || stack.members.length < 2) fail(`水平栈 ${stack.id} 至少需要两个成员。`);
    for (const member of stack.members) {
      if (!ids[member]) fail(`水平栈 ${stack.id} 引用了不存在的节点：${member}`);
      if (seenMembers[member]) fail(`节点 ${member} 不能同时属于多个水平栈。`);
      seenMembers[member] = true;
    }
    seenIds[stack.id] = true;
  });
}

function validateFreeTexts(items, version) {
  if (items === undefined) return;
  if (version < 3) fail("freeTexts 需要 schemaVersion 3。");
  if (!Array.isArray(items)) fail("freeTexts 必须是数组。");
  items.forEach((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item) || typeof item.t !== "string") fail(`freeTexts[${index}] 缺少 t。`);
    if (!finiteNumber(item.xr) || item.xr < 0 || item.xr > 1 || !finiteNumber(item.yr) || item.yr < 0 || item.yr > 1) fail(`freeTexts[${index}] 的 xr/yr 必须在 0..1。`);
    if (item.align !== undefined && item.align !== "left" && item.align !== "center" && item.align !== "right") fail(`freeTexts[${index}] 的 align 无效。`);
    if (item.vertical !== undefined && typeof item.vertical !== "boolean") fail(`freeTexts[${index}] 的 vertical 必须是布尔值。`);
    if (item.italic !== undefined && typeof item.italic !== "boolean") fail(`freeTexts[${index}] 的 italic 必须是布尔值。`);
    if (item.subItalic !== undefined && typeof item.subItalic !== "boolean") fail(`freeTexts[${index}] 的 subItalic 必须是布尔值。`);
  });
}

function unitLine(item) {
  return finiteNumber(item.x1) && item.x1 >= 0 && item.x1 <= 1 &&
    finiteNumber(item.y1) && item.y1 >= 0 && item.y1 <= 1 &&
    finiteNumber(item.x2) && item.x2 >= 0 && item.x2 <= 1 &&
    finiteNumber(item.y2) && item.y2 >= 0 && item.y2 <= 1;
}

function validateFreeLines(items, version) {
  if (items === undefined) return;
  if (version < 3) fail("freeLines 需要 schemaVersion 3。");
  if (!Array.isArray(items)) fail("freeLines 必须是数组。");
  items.forEach((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item) || !unitLine(item)) fail(`freeLines[${index}] 的 x1/y1/x2/y2 必须在 0..1。`);
    if (item.arrow !== undefined && !ARROWS[item.arrow]) fail(`freeLines[${index}] 的 arrow 无效。`);
    if (item.lineStyle !== undefined && item.lineStyle !== "solid" && item.lineStyle !== "dashed" && item.lineStyle !== "dotted") fail(`freeLines[${index}] 的 lineStyle 无效。`);
  });
}

function validateFreeDots(items, version) {
  if (items === undefined) return;
  if (version < 3) fail("freeDots 需要 schemaVersion 3。");
  if (!Array.isArray(items)) fail("freeDots 必须是数组。");
  items.forEach((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item) || !unitLine(item)) fail(`freeDots[${index}] 的 x1/y1/x2/y2 必须在 0..1。`);
    if (item.count !== undefined && (!finiteNumber(item.count) || item.count < 2 || Math.floor(item.count) !== item.count)) fail(`freeDots[${index}] 的 count 必须是大于 1 的整数。`);
    if (item.radius !== undefined && (!finiteNumber(item.radius) || item.radius <= 0)) fail(`freeDots[${index}] 的 radius 必须是正数。`);
  });
}

function containsCjk(text) {
  return /[\u3400-\u9FFF\uF900-\uFAFF]/.test(text || "");
}

function validateChineseDecisionLabels(root) {
  if (!root.nodes.some((node) => containsCjk(node.text))) return;
  const byId = Object.create(null);
  root.nodes.forEach((node) => { byId[node.id] = node; });
  const latinTruthLabels = { t: true, f: true, true: true, false: true, y: true, n: true, yes: true, no: true };
  root.edges.forEach((edge, index) => {
    const source = edge.from !== undefined ? byId[edge.from] : null;
    const label = typeof edge.label === "string" ? edge.label.trim().toLowerCase() : "";
    if (source && source.shape === "decision" && latinTruthLabels[label]) {
      fail(`[branch-language] 中文判断节点 ${source.id} 的连接 ${index + 1} 使用了 ${edge.label}；请改为“是”或“否”。`);
    }
  });
}

function validateCompactMergeRoutes(root) {
  const byId = Object.create(null);
  const byTarget = Object.create(null);
  root.nodes.forEach((node) => { byId[node.id] = node; });
  root.edges.forEach((edge, index) => {
    if (edge.from === undefined || edge.to === undefined) return;
    if (!byTarget[edge.to]) byTarget[edge.to] = [];
    byTarget[edge.to].push({ edge, index });
  });
  Object.keys(byTarget).forEach((targetId) => {
    const entries = byTarget[targetId];
    const target = byId[targetId];
    if (!target || entries.length < 2) return;
    const sources = entries.map((entry) => byId[entry.edge.from]).filter(Boolean);
    if (sources.length !== entries.length) return;
    const sourceRow = sources[0].row;
    const compactDownwardMerge = target.row === sourceRow + 1 &&
      sources.every((source) => source.row === sourceRow) &&
      entries.every((entry) => entry.edge.fromPort === "bottom" && entry.edge.toPort === "top");
    if (!compactDownwardMerge) return;
    entries.forEach((entry) => {
      if (!Array.isArray(entry.edge.via)) return;
      const hasSourceGap = entry.edge.via.some((point) => point.y === "from+gap" || point.y === "from-gap");
      const hasTargetGap = entry.edge.via.some((point) => point.y === "to+gap" || point.y === "to-gap");
      if (hasSourceGap && hasTargetGap) {
        fail(`[compact-merge] 连接 ${entry.index + 1} 汇入紧邻下一行的 ${targetId}，不要同时使用 from-gap/to+gap；省略 via 以使用中点汇流线。`);
      }
    });
  });
}

function validateNativeBranchBuses(root) {
  const byId = Object.create(null);
  const edgeById = Object.create(null);
  root.nodes.forEach((node) => { byId[node.id] = node; });
  root.edges.forEach((edge) => { if (edge.id !== undefined) edgeById[edge.id] = edge; });
  root.edges.forEach((edge, index) => {
    if (edge.fromEdge === undefined || edge.to === undefined) return;
    const parent = edgeById[edge.fromEdge];
    if (!parent || parent.from === undefined || parent.to === undefined) return;
    const source = byId[parent.from];
    const firstTarget = byId[parent.to];
    const secondTarget = byId[edge.to];
    if (source && firstTarget && secondTarget && firstTarget.row === source.row + 1 && secondTarget.row === firstTarget.row) {
      fail(`[branch-bus] 连接 ${index + 1} 把紧邻下一行的同排分支误写成 fromEdge；请改为两条同 from 的简单边以调用原生分支母线。`);
    }
  });
}

function validateNativeCombBusPorts(root) {
  const byId = Object.fromEntries(root.nodes.map((node) => [node.id, node]));
  const outgoing = Object.create(null);
  const incoming = Object.create(null);
  root.edges.forEach((edge, index) => {
    if (edge.from === undefined || edge.to === undefined) return;
    if (!outgoing[edge.from]) outgoing[edge.from] = [];
    if (!incoming[edge.to]) incoming[edge.to] = [];
    outgoing[edge.from].push({ edge, index });
    incoming[edge.to].push({ edge, index });
  });
  Object.keys(outgoing).forEach((sourceId) => {
    const source = byId[sourceId];
    if (!source) return;
    const entries = outgoing[sourceId].filter((entry) => {
      const target = byId[entry.edge.to];
      return target && target.row === source.row + 1;
    });
    if (entries.length >= 3 && entries.some((entry) => entry.edge.fromPort !== undefined)) fail(`[native-comb-bus] 节点 ${sourceId} 的同排多路分流必须省略显式端口，以使用 2 mm 梳状母线和 1 mm 紧凑框距。`);
  });
  Object.keys(incoming).forEach((targetId) => {
    const target = byId[targetId];
    if (!target) return;
    const entries = incoming[targetId].filter((entry) => {
      const source = byId[entry.edge.from];
      return source && source.row + 1 === target.row;
    });
    if (entries.length >= 3 && entries.some((entry) => entry.edge.fromPort !== undefined)) fail(`[native-comb-bus] 节点 ${targetId} 的同排多路汇流必须省略显式端口，以使用 2 mm 梳状母线和 1 mm 紧凑框距。`);
  });
}

function validateHorizontalStackConnections(root) {
  if (!Array.isArray(root.horizontalStacks)) return;
  const connected = Object.create(null);
  root.edges.forEach((edge) => {
    if (edge.from === undefined || edge.to === undefined) return;
    connected[`${edge.from}>${edge.to}`] = true;
    connected[`${edge.to}>${edge.from}`] = true;
  });
  root.horizontalStacks.forEach((stack) => {
    for (let index = 1; index < stack.members.length; index += 1) {
      const left = stack.members[index - 1];
      const right = stack.members[index];
      if (!connected[`${left}>${right}`]) {
        fail(`[horizontal-stack] 横向栈 ${stack.id} 的相邻成员 ${left} 与 ${right} 没有可见连接；不要用 horizontalStacks 压缩无关同行节点。`);
      }
    }
  });
}

function validateStackBranchCrossings(root) {
  if (!Array.isArray(root.stacks) || root.stacks.length === 0) return;
  const byId = Object.fromEntries(root.nodes.map((node) => [node.id, node]));
  const direct = new Set(root.edges
    .filter((edge) => edge && edge.from !== undefined && edge.to !== undefined)
    .map((edge) => `${edge.from}\u0000${edge.to}`));
  root.stacks.forEach((stack) => {
    for (let index = 1; index < stack.members.length; index += 1) {
      const source = byId[stack.members[index - 1]];
      const target = byId[stack.members[index]];
      if (target.row <= source.row + 1) continue;
      const bridges = root.nodes.filter((node) =>
        node.row > source.row && node.row < target.row &&
        direct.has(`${source.id}\u0000${node.id}`) &&
        direct.has(`${node.id}\u0000${target.id}`));
      if (bridges.length > 0) {
        fail(`[stack-branch-crossing] 纵向栈 ${stack.id} 的 ${source.id} -> ${target.id} 跨过分支层 ${bridges.map((node) => node.id).join(", ")}；请拆分或移除该 stack，保留网格行的分流与汇流顺序。`);
      }
    }
  });
}

function validateReciprocalEdges(edges) {
  const directed = Object.create(null);
  for (const edge of edges) if (edge.from !== undefined && edge.to !== undefined) directed[`${edge.from}>${edge.to}`] = edge;
  const checked = Object.create(null);
  for (const edge of edges) {
    if (edge.fromEdge !== undefined || edge.toEdge !== undefined) continue;
    const pairKey = [edge.from, edge.to].sort().join("<>");
    if (checked[pairKey]) continue;
    checked[pairKey] = true;
    const reverse = directed[`${edge.to}>${edge.from}`];
    if (!reverse) continue;
    const separated =
      (edge.fromPort !== undefined && edge.fromPort === edge.toPort) ||
      (reverse.fromPort !== undefined && reverse.fromPort === reverse.toPort) ||
      edge.via !== undefined || reverse.via !== undefined;
    if (!separated) fail(`[reciprocal] 互反连接 ${edge.from}<->${edge.to} 会重合；schemaVersion 2 中至少一条边必须使用同侧显式端口形成外绕回环。`);
  }
}

function validateLength(value, expected, name) {
  if (!Array.isArray(value)) fail(`${name} 必须是数组。`);
  if (value.length !== expected) fail(`${name} 长度必须等于 ${expected}。`);
}

function validateNumericLength(value, expected, name) {
  validateLength(value, expected, name);
  value.forEach((item, index) => {
    if (!finiteNumber(item)) fail(`${name}[${index}] 必须是有限数字；不要用 null 表示缺失点。`);
  });
}

function validateOptionalLength(value, expected, name) {
  if (value === undefined || typeof value === "number") return;
  validateLength(value, expected, name);
}

function validateOptionalNumericLength(value, expected, name) {
  if (value === undefined || typeof value === "number") return;
  validateNumericLength(value, expected, name);
}

function validateBand(band, expected, chartIndex, name) {
  if (!band || typeof band !== "object" || Array.isArray(band)) fail(`chart ${chartIndex}: ${name} 必须是对象。`);
  validateNumericLength(band.low, expected, `chart ${chartIndex}: ${name}.low`);
  validateNumericLength(band.high, expected, `chart ${chartIndex}: ${name}.high`);
}

function validateChartSeries(chart, expected, chartIndex) {
  if (!Array.isArray(chart.series)) fail(`chart ${chartIndex}: 缺少 series。`);
  chart.series.forEach((series, seriesIndex) => {
    if (!series || typeof series !== "object" || Array.isArray(series)) fail(`chart ${chartIndex} series ${seriesIndex + 1}: 必须是对象。`);
    if (series.name !== undefined && typeof series.name !== "string") fail(`chart ${chartIndex} series ${seriesIndex + 1}: name 必须是字符串。`);
    if (series.data !== undefined) validateNumericLength(series.data, expected, `chart ${chartIndex} series ${seriesIndex + 1}: data`);
    validateOptionalNumericLength(series.error, expected, `chart ${chartIndex} series ${seriesIndex + 1}: error`);
    validateOptionalNumericLength(series.err, expected, `chart ${chartIndex} series ${seriesIndex + 1}: err`);
    validateOptionalNumericLength(series.errors, expected, `chart ${chartIndex} series ${seriesIndex + 1}: errors`);
    validateOptionalNumericLength(series.errorLow, expected, `chart ${chartIndex} series ${seriesIndex + 1}: errorLow`);
    validateOptionalNumericLength(series.errorHigh, expected, `chart ${chartIndex} series ${seriesIndex + 1}: errorHigh`);
    validateOptionalLength(series.labels, expected, `chart ${chartIndex} series ${seriesIndex + 1}: labels`);
    validateOptionalLength(series.valueLabels, expected, `chart ${chartIndex} series ${seriesIndex + 1}: valueLabels`);
    if (series.band !== undefined) validateBand(series.band, expected, chartIndex, `series ${seriesIndex + 1} band`);
  });
}

function validateChartLines(chart, chartIndex) {
  const lines = chart.thresholds || chart.hLines;
  if (lines === undefined) return;
  if (!Array.isArray(lines)) fail(`chart ${chartIndex}: thresholds 必须是数组。`);
  lines.forEach((line, lineIndex) => {
    if (typeof line === "number") return;
    if (!line || !finiteNumber(line.y)) fail(`chart ${chartIndex} threshold ${lineIndex + 1}: 缺少数字 y。`);
    if (line.label !== undefined && typeof line.label !== "string") fail(`chart ${chartIndex} threshold ${lineIndex + 1}: label 必须是字符串。`);
  });
}

function validateBox(box, chartIndex, boxIndex) {
  const values = Array.isArray(box) ? box : (box && typeof box === "object" ? [box.min, box.q1, box.median, box.q3, box.max] : null);
  if (!values || values.length < 5) fail(`chart ${chartIndex} box ${boxIndex}: 缺少 min/q1/median/q3/max。`);
  values.slice(0, 5).forEach((value) => {
    if (!finiteNumber(value)) fail(`chart ${chartIndex} box ${boxIndex}: 五数摘要必须是数字。`);
  });
}

function validateChartRenderMode(item, label) {
  if (item.renderMode !== undefined && item.renderMode !== "textOnly" && item.renderMode !== "plot") {
    fail(`${label}: renderMode 只能是 textOnly 或 plot。`);
  }
  if (item.textOnly !== undefined && typeof item.textOnly !== "boolean") {
    fail(`${label}: textOnly 必须是布尔值。`);
  }
}

function validateStatChart(root) {
  validateChartRenderMode(root, "statChart");
  if (root.schemaVersion !== 3) fail("statChart 需要 schemaVersion 3。");
  if (!Array.isArray(root.charts) || root.charts.length === 0) fail("statChart 必须有非空 charts 数组。");
  if (root.cols !== undefined && (!Number.isInteger(root.cols) || root.cols < 1)) fail("statChart.cols 必须是正整数。");
  root.charts.forEach((chart, index) => {
    const chartIndex = index + 1;
    validateChartRenderMode(chart, `chart ${chartIndex}`);
    if (!chart || typeof chart !== "object" || Array.isArray(chart)) fail(`chart ${chartIndex}: 必须是对象。`);
    if (typeof chart.title !== "string") fail(`chart ${chartIndex}: 缺少 title。`);
    if (typeof chart.yLabel !== "string") fail(`chart ${chartIndex}: 缺少 yLabel。`);
    const hasTicks = Array.isArray(chart.yTicks) && chart.yTicks.length > 0;
    const hasRange = finiteNumber(chart.yMin) && finiteNumber(chart.yMax) && finiteNumber(chart.yStep);
    if (!hasTicks && !hasRange) fail(`chart ${chartIndex}: 必须提供 yTicks 或 yMin/yMax/yStep。`);
    if (hasTicks) chart.yTicks.forEach((tick, tickIndex) => {
      if (!finiteNumber(tick)) fail(`chart ${chartIndex}: yTicks[${tickIndex}] 必须是有限数字。`);
    });
    if (hasTicks && chart.yTicks.length < 2 && !hasRange) fail(`chart ${chartIndex}: 绘制数据时至少需要两项 yTicks，或提供 yMin/yMax/yStep。`);
    if (hasRange && chart.yMax <= chart.yMin) fail(`chart ${chartIndex}: yMax 必须大于 yMin。`);
    if (hasRange && chart.yStep <= 0) fail(`chart ${chartIndex}: yStep 必须为正数。`);
    validateChartLines(chart, chartIndex);
    if (chart.type === "bar") {
      if (!Array.isArray(chart.xCats) || chart.xCats.length === 0) fail(`chart ${chartIndex}: 柱状图需要 xCats。`);
      validateChartSeries(chart, chart.xCats.length, chartIndex);
    } else if (chart.type === "box" || chart.type === "boxplot") {
      if (!Array.isArray(chart.xCats) || chart.xCats.length === 0) fail(`chart ${chartIndex}: 箱线图需要 xCats。`);
      validateLength(chart.boxes, chart.xCats.length, `chart ${chartIndex}: boxes`);
      chart.boxes.forEach((box, boxIndex) => validateBox(box, chartIndex, boxIndex + 1));
    } else {
      if (chart.type !== undefined && chart.type !== "line") fail(`chart ${chartIndex}: 不支持 type ${chart.type}。`);
      if (!Array.isArray(chart.xTicks) || chart.xTicks.length === 0) fail(`chart ${chartIndex}: 折线图需要 xTicks。`);
      chart.xTicks.forEach((tick, tickIndex) => {
        if (!finiteNumber(tick)) fail(`chart ${chartIndex}: xTicks[${tickIndex}] 必须是数字；分类文字请放入 xTickLabels。`);
      });
      if (chart.xTickLabels !== undefined) {
        if (!Array.isArray(chart.xTickLabels) || chart.xTickLabels.length !== chart.xTicks.length) fail(`chart ${chartIndex}: xTickLabels 长度必须等于 xTicks。`);
        chart.xTickLabels.forEach((label, labelIndex) => {
          if (typeof label !== "string") fail(`chart ${chartIndex}: xTickLabels[${labelIndex}] 必须是字符串。`);
        });
      }
      validateChartSeries(chart, chart.xTicks.length, chartIndex);
      if (chart.band !== undefined) validateBand(chart.band, chart.xTicks.length, chartIndex, "band");
    }
  });
}

function validateModuleTree(root) {
  if (root.layoutMode !== "compact") fail("[module-tree] 模块树必须使用 layoutMode: compact。");
  if (root.fontSize !== 8) fail("[module-tree] 模块树必须显式使用固定 8 pt 字号。");
  if (root.flowShapePolicy !== "sourceVisible") fail("[module-tree] 模块树必须使用 flowShapePolicy: sourceVisible，避免自动替换端点形状。");

  const byId = Object.create(null);
  const outgoing = Object.create(null);
  const incoming = Object.create(null);
  const children = Object.create(null);
  root.nodes.forEach((node) => {
    byId[node.id] = node;
    outgoing[node.id] = 0;
    incoming[node.id] = 0;
    children[node.id] = [];
  });
  root.edges.forEach((edge) => {
    if (edge.fromEdge !== undefined || edge.toEdge !== undefined) fail("[module-tree] 模块树只允许节点到节点的直接连接。");
    if (edge.arrow !== "none") fail("[module-tree] 模块树连接必须显式设置 arrow: none。");
    outgoing[edge.from] += 1;
    incoming[edge.to] += 1;
    children[edge.from].push(edge.to);
  });

  const roots = [];
  const leaves = [];
  const branches = [];
  let leafHeightGroup;
  let leafRow;
  let branchHeightGroup;
  let leafWidthGroup;
  let branchRow;
  let minLeafColumn;
  let maxLeafColumn;
  root.nodes.forEach((node) => {
    if (incoming[node.id] === 0) roots.push(node);
    if (outgoing[node.id] === 0) {
      if (node.textDirection !== "vertical") fail(`[module-tree] 叶节点 ${node.id} 必须使用 vertical 文字。`);
      if (!node.heightGroup) fail(`[module-tree] 叶节点 ${node.id} 必须设置公共 heightGroup。`);
      if (!node.widthGroup) fail(`[module-tree] 叶节点 ${node.id} 必须设置公共 widthGroup。`);
      if (leafHeightGroup === undefined) leafHeightGroup = node.heightGroup;
      else if (leafHeightGroup !== node.heightGroup) fail("[module-tree] 所有叶节点必须共享同一个 heightGroup。");
      if (leafWidthGroup === undefined) leafWidthGroup = node.widthGroup;
      else if (leafWidthGroup !== node.widthGroup) fail("[module-tree] 所有叶节点必须共享同一个 widthGroup。");
      if (leafRow === undefined) leafRow = node.row;
      else if (leafRow !== node.row) fail("[module-tree] 所有叶节点必须位于同一终端行。");
      minLeafColumn = minLeafColumn === undefined ? node.column : Math.min(minLeafColumn, node.column);
      maxLeafColumn = maxLeafColumn === undefined ? node.column : Math.max(maxLeafColumn, node.column);
      leaves.push(node);
    } else if (incoming[node.id] > 0) {
      if (!node.heightGroup) fail(`[module-tree] 模块标题 ${node.id} 必须设置公共 heightGroup。`);
      if (branchHeightGroup === undefined) branchHeightGroup = node.heightGroup;
      else if (branchHeightGroup !== node.heightGroup) fail("[module-tree] 同层模块标题必须共享同一个 heightGroup。");
      if (branchRow === undefined) branchRow = node.row;
      else if (branchRow !== node.row) fail("[module-tree] 模块标题必须位于同一行。");
      branches.push(node);
    }
  });
  if (leaves.length === 0) fail("[module-tree] 模块树至少需要一个叶节点。");
  if (roots.length !== 1) fail("[module-tree] 模块树必须且只能有一个根节点。");
  const rootColumn = (minLeafColumn + maxLeafColumn) / 2;
  if (roots[0].column !== rootColumn) fail(`[module-tree] 根节点必须位于全部叶节点跨度的中心 column ${rootColumn}。`);

  const leafGroups = branches.map((branch) => {
    let minColumn;
    let maxColumn;
    const allLeaves = children[branch.id].length > 0 && children[branch.id].every((childId) => {
      const child = byId[childId];
      minColumn = minColumn === undefined ? child.column : Math.min(minColumn, child.column);
      maxColumn = maxColumn === undefined ? child.column : Math.max(maxColumn, child.column);
      return outgoing[child.id] === 0;
    });
    if (!allLeaves) fail(`[module-tree] 模块标题 ${branch.id} 的直接子项必须全部是叶节点。`);
    const expectedColumn = (minColumn + maxColumn) / 2;
    if (branch.column !== expectedColumn) fail(`[module-tree] 模块标题 ${branch.id} 必须位于子项跨度的中心 column ${expectedColumn}。`);
    return { min: minColumn, max: maxColumn, id: branch.id };
  }).sort((a, b) => a.min - b.min);
}

function looksLikeModuleTree(root) {
  if (root.kind !== "flowchart" || root.treeLayout === "module" || root.nodes.length < 7) return false;
  const byId = Object.fromEntries(root.nodes.map((node) => [node.id, node]));
  const incoming = Object.fromEntries(root.nodes.map((node) => [node.id, 0]));
  const outgoing = Object.fromEntries(root.nodes.map((node) => [node.id, []]));
  root.edges.forEach((edge) => {
    if (edge.from === undefined || edge.to === undefined || !byId[edge.from] || !byId[edge.to]) return;
    incoming[edge.to] += 1;
    outgoing[edge.from].push(edge.to);
  });
  const roots = root.nodes.filter((node) => incoming[node.id] === 0);
  const leaves = root.nodes.filter((node) => outgoing[node.id].length === 0);
  const branches = root.nodes.filter((node) => outgoing[node.id].length > 0 && incoming[node.id] > 0);
  if (roots.length !== 1 || branches.length < 2 || leaves.length < 4) return false;
  if (branches.some((node) => outgoing[node.id].length < 2)) return false;
  if (branches.some((node) => node.row !== branches[0].row || outgoing[node.id].some((childId) => outgoing[childId].length !== 0))) return false;
  if (leaves.some((node) => node.textDirection !== "vertical" || node.row !== leaves[0].row)) return false;
  return outgoing[roots[0].id].length === branches.length && branches.every((node) => outgoing[roots[0].id].indexOf(node.id) >= 0);
}

function validate(root) {
  if(root.kind === "technical") return require("./technical-schema.cjs").validateTechnical(root);
  if (!root || typeof root !== "object" || Array.isArray(root)) fail("根对象无效。");
  if (root.schemaVersion !== 1 && root.schemaVersion !== 2 && root.schemaVersion !== 3) fail("仅支持 schemaVersion 1、2 或 3。");
  if (root.kind !== "flowchart" && root.kind !== "blockDiagram" && root.kind !== "signalFlow" && root.kind !== "freeform" && root.kind !== "statChart") fail("kind 只能是 flowchart、blockDiagram、signalFlow、freeform 或 statChart。");
  if (root.kind === "statChart") {
    validateStatChart(root);
    return root;
  }
  if (root.flowShapePolicy !== undefined && root.flowShapePolicy !== "endpointsRounded" && root.flowShapePolicy !== "sourceVisible") fail("flowShapePolicy 只能是 endpointsRounded 或 sourceVisible。");
  if (root.schemaVersion < 3 && root.kind !== "flowchart") fail("blockDiagram、signalFlow 和 freeform 需要 schemaVersion 3。");
  if (root.widthClass !== undefined && root.widthClass !== "single" && root.widthClass !== "double") fail("widthClass 只能是 single 或 double。");
  if (root.fontSize !== undefined && ![8, 7, 6].includes(root.fontSize)) fail("fontSize 只能是 8、7 或 6。");
  if (root.layoutMode !== undefined && root.layoutMode !== "standard" && root.layoutMode !== "compact") fail("layoutMode 只能是 standard 或 compact。");
  if (root.schemaVersion < 3 && root.layoutMode !== undefined) fail("layoutMode 需要 schemaVersion 3。");
  if (root.treeLayout !== undefined && root.treeLayout !== "module") fail("treeLayout 只能是 module。");
  if (root.treeLayout !== undefined && (root.schemaVersion < 3 || root.kind !== "flowchart")) fail("treeLayout 需要 schemaVersion 3 的 flowchart。");
  if (root.sideLabelBand !== undefined && root.sideLabelBand !== "layerLabels") fail("sideLabelBand 只能是 layerLabels。");
  if (root.sideLabelBand !== undefined && (root.schemaVersion < 3 || root.kind !== "blockDiagram")) fail("sideLabelBand 需要 schemaVersion 3 的 blockDiagram。");
  if (!Array.isArray(root.nodes) || (root.nodes.length === 0 && !(Array.isArray(root.freeTexts) && root.freeTexts.length))) fail("nodes 必须是非空数组；纯自由文字图可改用 freeTexts。");
  if (!Array.isArray(root.edges)) fail("edges 必须是数组。");

  const ids = Object.create(null);
  root.nodes.forEach((node, index) => validateNode(node, index, ids, root.schemaVersion, root.kind));
  const endpointIds = Object.assign(Object.create(null), ids);
  validateContainers(root.containers, ids, endpointIds, root.schemaVersion, root.nodes);
  validateSwimlaneLayout(root, ids);
  validateStacks(root.stacks, ids, root.schemaVersion);
  validateHorizontalStacks(root.horizontalStacks, ids, root.schemaVersion);
  validateFreeTexts(root.freeTexts, root.schemaVersion);
  validateFreeLines(root.freeLines, root.schemaVersion);
  validateFreeDots(root.freeDots, root.schemaVersion);
  const edgeIds = Object.create(null);
  root.edges.forEach((edge, index) => {
    if (edge && edge.id !== undefined) {
      if (!validId(edge.id) || edgeIds[edge.id] !== undefined) fail(`连接 ${index + 1} 的 id 无效或重复。`);
      edgeIds[edge.id] = index;
    }
  });
  root.edges.forEach((edge, index) => validateEdge(edge, index, endpointIds, edgeIds, root.schemaVersion, root.kind));
  const textOnlyIds = new Set(root.nodes.filter((node) => node.shape === "label").map((node) => node.id));
  root.edges.forEach((edge) => {
    if (textOnlyIds.has(edge.from) || textOnlyIds.has(edge.to)) fail("[text-only-node] 连接不能以 label 文字节点作为端点。");
  });
  validateChineseDecisionLabels(root);
  validateCompactMergeRoutes(root);
  validateNativeBranchBuses(root);
  validateNativeCombBusPorts(root);
  validateHorizontalStackConnections(root);
  validateStackBranchCrossings(root);
  validateReciprocalEdges(root.edges);
  if (looksLikeModuleTree(root)) fail("[module-tree-config] 该图是单根、多模块、末级竖排子项的模块树；必须设置 treeLayout: \"module\"，不要让普通网格布局处理。");
  if (root.treeLayout === "module") validateModuleTree(root);
  return root;
}

function main(argv) {
  if (argv.length !== 1) fail("用法：node validate_flowchart.js <file.flowchart.json>");
  const text = fs.readFileSync(argv[0], "utf8").replace(/^\uFEFF/, "");
  const root = JSON.parse(text);
  validate(root);
  if (root.kind === "technical") process.stdout.write("PASS: technical " + root.layout + String.fromCharCode(10));
  else if (root.kind === "statChart") process.stdout.write(`PASS: ${root.charts.length} charts, schemaVersion ${root.schemaVersion}.\n`);
  else process.stdout.write(`PASS: ${root.nodes.length} nodes, ${root.edges.length} edges, schemaVersion ${root.schemaVersion}.\n`);
}

try {
  main(process.argv.slice(2));
} catch (error) {
  process.stderr.write(`FAIL: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
