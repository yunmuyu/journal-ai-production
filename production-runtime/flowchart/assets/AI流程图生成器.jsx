#target illustrator
// allow: SIZE_OK - Illustrator CC 2019 requires this generator to remain a self-contained ExtendScript entrypoint.
// allow: SIZE_OK — Illustrator 2019 menu scripts are deployed as one self-contained JSX entry.

(function () {
    if (app.documents.length === 0) { alert("请先打开 Illustrator 文档。"); return; }

    var doc = app.activeDocument;
    var layer = doc.activeLayer;
    if (layer.locked || !layer.visible) { alert("当前图层被锁定或隐藏，请切换到可编辑图层。"); return; }

    var PT_PER_MM = 2.83464566929;
    var CFG = {
        GAP: 3 * PT_PER_MM,
        BUS_LEG: 2 * PT_PER_MM,
        COLUMN_GAP_STANDARD: 3 * PT_PER_MM,
        COLUMN_GAP_COMPACT: 1.5 * PT_PER_MM,
        GAP_MINIMAL: 1 * PT_PER_MM,
        CONTAINER_PAD_MINIMAL: 1 * PT_PER_MM,
        CONTAINER_PAD_TIGHT: 3 * PT_PER_MM,
        CONTAINER_PAD_NORMAL: 6 * PT_PER_MM,
        CONTAINER_ROUND_RADIUS: 5 * PT_PER_MM,
        SWIMLANE_HEADER_HEIGHT: 7 * PT_PER_MM,
        LAYER_LABEL_BAND: 15 * PT_PER_MM,
        BRANCH_SEGMENTS: 2,
        STROKE: 0.5,
        FONT_SIZES: [8, 7, 6],
        MATH_FONTS: ["TimesNewRomanPS-ItalicMT", "Times New Roman Italic", "TimesNewRomanPS-Italic", "TimesNewRoman"],
        MATH_SUB_FONTS: ["TimesNewRomanPSMT", "Times New Roman", "TimesNewRoman"],
        LEADING_6: 7,
        PAD_X: 4.5,
        PAD_Y: 2.7,
        HORIZONTAL_BOX_HEIGHT: 15.2,
        HORIZONTAL_CHAR_WIDTH: 8,
        HORIZONTAL_PADDING_TOTAL: 9,
        VERTICAL_BOX_WIDTH: 13.9,
        VERTICAL_LINE_HEIGHT: 9.6,
        VERTICAL_PADDING_TOTAL: 3.1,
        DECISION_HALF_WIDTH: 29.4,
        DECISION_HALF_HEIGHT: 9.9,
        DECISION_MULTILINE_PADDING_X: 34,
        DECISION_MULTILINE_PADDING_Y: 27,
        OPERATOR_SIZE: 4.0 * PT_PER_MM,
        OPERATOR_STROKE: 0.6,
        OPERATOR_GAP: 0.18 * PT_PER_MM,
        ARROW_SYMBOL_WIDTH: 2.5 * PT_PER_MM,
        ARROW_SYMBOL_HEIGHT: 2.5 * PT_PER_MM,
        BRACE_SYMBOL_WIDTH: 2.5 * PT_PER_MM,
        BRACE_SYMBOL_HEIGHT: 12.0 * PT_PER_MM,
        ELLIPSE_SCALE_X: 1.2,
        ELLIPSE_SCALE_Y: 1.2,
        CYLINDER_WIDTH: 33.8,
        CYLINDER_HEIGHT: 15.2,
        CYLINDER_RIM_HEIGHT: 2.6,
        WIDE_NESTED_WIDTH: 183.5,
        WIDE_NESTED_HEIGHT: 34.4,
        WIDE_NESTED_PAD_X: 3 * PT_PER_MM,
        WIDE_NESTED_PAD_TOP: 2 * PT_PER_MM,
        BOTTOM_LABEL_PAD_TOP: 2 * PT_PER_MM,
        SINGLE_COLUMN_WIDTH: 80 * PT_PER_MM,
        MARGIN: 12,
        ARROW_W: 3.7,
        ARROW_H: 4.4,
        ARROW_NOTCH: 0.8
    };

    var sample = readSibling("figure-4-recovery-menu.flowchart.json");
    var input = askJson(sample || '{\n  "schemaVersion": 3,\n  "kind": "flowchart",\n  "nodes": [],\n  "edges": []\n}');
    if (input === null) return;

    var data;
    try { data = parseInputData(input); if(data.kind !== "technical") validate(data); }
    catch (e) { alert("JSON 校验失败：\n" + e); return; }

    if (data.kind === "technical") {
        var technicalFont = resolveFont().font, technicalBlack = gray(100), technicalWhite = gray(0), technicalAll = [];
        var technicalBoard = doc.artboards[doc.artboards.getActiveArtboardIndex()].artboardRect;
        JFW.drawTechnicalLayout(data, {
            measure:function(t){return measureContainerTitle(t,data.fontSize,technicalFont);},
            text:function(id,t,x,y){var tf=createText(t,x,y,data.fontSize,technicalFont,technicalBlack);tf.name="AI_TECH_TEXT_"+id;},
            node:function(id,t,shape,x,y,w,h){drawNodes([{id:id,text:t,shape:shape,cx:x,cy:y,w:w,h:h,left:x-w/2,right:x+w/2,top:y+h/2,bottom:y-h/2}],layer,technicalBlack,technicalWhite,technicalAll,data.fontSize,technicalFont);},
            line:function(id,points,arrow,style){addRoutedLine(layer,points,arrow,technicalBlack,technicalAll,style);},
            image:function(id,file,cx,y,w,h){var p=layer.placedItems.add();p.file=new File(file);var factor=Math.min(w/p.width,h/p.height);p.width*=factor;p.height*=factor;p.left=cx-p.width/2;p.top=-y-(h-p.height)/2;p.name="AI_TECH_IMAGE_"+id;p.embed();}
        },technicalBoard[2]-technicalBoard[0]-0.5);
        return;
    }

    if (data.kind === "statChart") {
        drawStatChart(data);
        return;
    }

    var fontInfo = resolveFont();
    var ab = doc.artboards[doc.artboards.getActiveArtboardIndex()].artboardRect;
    var availableW = ab[2] - ab[0] - CFG.MARGIN * 2;
    var maxW = data.widthClass === "double" ? availableW : Math.min(CFG.SINGLE_COLUMN_WIDTH, availableW);
    var maxH = ab[1] - ab[3] - CFG.MARGIN * 2;
    var layout = chooseLayout(data, maxW, maxH, fontInfo.font);
    if (!layout) {
        alert("流程图布局计算失败，未生成图件。");
        return;
    }

    positionLayout(layout, ab);
    assertNodeSeparation(layout.nodes);

    try { validateRoutedEdges(data.edges, layout.edgeById, layout); }
    catch (routeError) { alert("连接路径校验失败：\n" + routeError); return; }

    var black = gray(100), white = gray(0), created = [];
    drawContainers(layout.containers, layer, black, created, layout.fontSize, fontInfo.font);
    drawEdges(data.edges, layout.edgeById, layout, layer, black, created, layout.fontSize, fontInfo.font);
    drawNodes(layout.nodes, layer, black, white, created, layout.fontSize, fontInfo.font);
    drawFreeLines(data.freeLines || [], layout, layer, black, created);
    drawFreeDots(data.freeDots || [], layout, layer, black, created);
    drawFreeTexts(data.freeTexts || [], layout, layer, black, created);
    app.redraw();

    doc.selection = null;
    var i;
    for (i = 0; i < created.length; i++) {
        try { created[i].selected = true; } catch (ignore) {}
    }

    var fontNote = fontInfo.composite
        ? "已连接复合字体“现 宋体 1”。"
        : (fontInfo.font ? "未连接复合字体，已回退宋体。" : "未找到复合字体或宋体，已保留 Illustrator 默认字体。");
    alert("流程图生成器 3.0 已生成：" + data.nodes.length + " 个节点，" + data.edges.length + " 条连接。\n" +
          "统一字号 " + layout.fontSize + " pt；直连 3 mm，汇总线上下各 3 mm；线宽 0.5 pt。\n" + fontNote + "\n" +
          "已保留字符级字体、斜体和上下标属性。" );

    function validate(root) {
        if (!root || (root.schemaVersion !== 1 && root.schemaVersion !== 2 && root.schemaVersion !== 3)) throw "仅支持 schemaVersion 1、2 或 3。";
        if (root.kind !== "flowchart" && root.kind !== "blockDiagram" && root.kind !== "signalFlow" && root.kind !== "freeform" && root.kind !== "statChart") throw "kind 只能是 flowchart、blockDiagram、signalFlow、freeform 或 statChart。";
        if (root.kind === "statChart") { validateStatChart(root); return; }
        if (root.schemaVersion < 3 && root.kind !== "flowchart") throw "blockDiagram、signalFlow 和 freeform 需要 schemaVersion 3。";
        if (root.widthClass !== undefined && root.widthClass !== "single" && root.widthClass !== "double") throw "widthClass 只能是 single 或 double。";
        if (root.fontSize !== undefined && root.fontSize !== 8 && root.fontSize !== 7 && root.fontSize !== 6) throw "fontSize 只能是 8、7 或 6。";
        if (root.layoutMode !== undefined && root.layoutMode !== "standard" && root.layoutMode !== "compact") throw "layoutMode 只能是 standard 或 compact。";
        if (root.schemaVersion < 3 && root.layoutMode !== undefined) throw "layoutMode 需要 schemaVersion 3。";
        if (root.treeLayout !== undefined && root.treeLayout !== "module") throw "treeLayout 只能是 module。";
        if (root.treeLayout !== undefined && (root.schemaVersion < 3 || root.kind !== "flowchart")) throw "treeLayout 需要 schemaVersion 3 的 flowchart。";
        if (root.sideLabelBand !== undefined && root.sideLabelBand !== "layerLabels") throw "sideLabelBand 只能是 layerLabels。";
        if (root.sideLabelBand !== undefined && (root.schemaVersion < 3 || root.kind !== "blockDiagram")) throw "sideLabelBand 需要 schemaVersion 3 的 blockDiagram。";
        if (!(root.nodes instanceof Array) || (root.nodes.length === 0 && !(root.freeTexts instanceof Array && root.freeTexts.length))) throw "nodes 必须是非空数组；纯自由文字图可改用 freeTexts。";
        if (!(root.edges instanceof Array)) throw "edges 必须是数组。";
        if (root.freeTexts !== undefined && (!(root.freeTexts instanceof Array) || root.schemaVersion < 3)) throw "freeTexts 必须是 schemaVersion 3 数组。";
        if (root.freeLines !== undefined && (!(root.freeLines instanceof Array) || root.schemaVersion < 3)) throw "freeLines 必须是 schemaVersion 3 数组。";
        if (root.freeDots !== undefined && (!(root.freeDots instanceof Array) || root.schemaVersion < 3)) throw "freeDots 必须是 schemaVersion 3 数组。";
        if (root.containers !== undefined && !(root.containers instanceof Array)) throw "containers 必须是数组。";
        if (root.schemaVersion < 3 && root.containers !== undefined) throw "containers 需要 schemaVersion 3。";
        if (root.stacks !== undefined && !(root.stacks instanceof Array)) throw "stacks 必须是数组。";
        if (root.schemaVersion < 3 && root.stacks !== undefined) throw "stacks 需要 schemaVersion 3。";
        if (root.horizontalStacks !== undefined && !(root.horizontalStacks instanceof Array)) throw "horizontalStacks 必须是数组。";
        if (root.schemaVersion < 3 && root.horizontalStacks !== undefined) throw "horizontalStacks 需要 schemaVersion 3。";
        if (root.swimlaneLayout !== undefined && root.swimlaneLayout !== "vertical" && root.swimlaneLayout !== "horizontal") throw "swimlaneLayout 只能是 vertical 或 horizontal。";
        if (root.swimlaneLayout !== undefined && (root.schemaVersion < 3 || root.kind !== "flowchart")) throw "swimlaneLayout 需要 schemaVersion 3 的 flowchart。";
        var ids = {}, endpointIds = {}, textOnlyIds = {}, rowById = {}, shapes = { terminator: 1, process: 1, decision: 1, ellipse: 1, cylinder: 1, arrow: 1, brace: 1, plusCircle: 1, minusCircle: 1, label: 1, functionBlock: 1, multiplier: 1, summer: 1, port: 1, waveBlock: 1, sideCurveBlock: 1, inputOutput: 1, predefinedProcess: 1 };
        var ports = { top: 1, right: 1, bottom: 1, left: 1 };
        var labelPositions = { source: 1, middle: 1, target: 1 };
        var arrows = { none: 1, start: 1, end: 1, both: 1 };
        var labelSides = { above: 1, below: 1, left: 1, right: 1 };
        var lineStyles = { solid: 1, dashed: 1, dotted: 1 };
        var routeStyles = { straight: 1, orthogonal: 1, curve: 1 };
        var portPositions = { center: 1, upper: 1, lower: 1, left: 1, right: 1 };
        var directed = {}, checked = {}, edgeIds = {}, i, n, e, lines, longest, j, key, reverse, separated, hasFrom, hasFromEdge, hasTo, hasToEdge;
        for (i = 0; i < root.nodes.length; i++) {
            n = root.nodes[i];
            if (!n || !/^[A-Za-z][A-Za-z0-9_-]*$/.test(n.id || "")) throw "节点 " + (i + 1) + " 的 id 无效。";
            if (ids[n.id]) throw "节点 id 重复：" + n.id;
            if (!shapes[n.shape]) throw "节点 " + n.id + " 的 shape 无效。";
            if (typeof n.text !== "string" || (n.text === "" && n.shape !== "multiplier" && n.shape !== "summer" && n.shape !== "port" && n.shape !== "arrow" && n.shape !== "brace" && n.shape !== "plusCircle" && n.shape !== "minusCircle")) throw "节点 " + n.id + " 缺少 text。";
            if ((n.shape === "functionBlock" || n.shape === "multiplier" || n.shape === "summer" || n.shape === "port") && (root.schemaVersion < 3 || root.kind !== "signalFlow")) throw "节点 " + n.id + " 的 signalFlow 专用 shape 需要 schemaVersion 3 的 signalFlow。";
            if (n.shape === "label" && (root.schemaVersion < 3 || root.kind !== "blockDiagram")) throw "节点 " + n.id + " 的 label shape 需要 schemaVersion 3 的 blockDiagram。";
            if (!isFiniteNumber(n.row) || n.row < 0 || Math.floor(n.row) !== n.row) throw "节点 " + n.id + " 的 row 必须是非负整数。";
            if (!isFiniteNumber(n.column) || n.column < 0 || Math.round(n.column * 2) !== n.column * 2) throw "节点 " + n.id + " 的 column 必须是非负整数或半整数。";
            if (n.textDirection !== undefined && n.textDirection !== "horizontal" && n.textDirection !== "vertical") throw "节点 " + n.id + " 的 textDirection 无效。";
            if (n.arrowDirection !== undefined && n.arrowDirection !== "right" && n.arrowDirection !== "left" && n.arrowDirection !== "up" && n.arrowDirection !== "down") throw "节点 " + n.id + " 的 arrowDirection 无效。";
            if (n.arrowHeads !== undefined && n.arrowHeads !== "end" && n.arrowHeads !== "both") throw "节点 " + n.id + " 的 arrowHeads 无效。";
            if ((n.arrowDirection !== undefined || n.arrowHeads !== undefined) && n.shape !== "arrow") throw "节点 " + n.id + " 的 arrowDirection/arrowHeads 只适用于 arrow。";
            if (n.braceSide !== undefined && n.braceSide !== "left" && n.braceSide !== "right" && n.braceSide !== "top" && n.braceSide !== "bottom") throw "节点 " + n.id + " 的 braceSide 无效。";
            if (n.braceSide !== undefined && n.shape !== "brace") throw "节点 " + n.id + " 的 braceSide 只适用于 brace。";
            if (n.heightGroup !== undefined && !/^[A-Za-z][A-Za-z0-9_-]*$/.test(n.heightGroup)) throw "节点 " + n.id + " 的 heightGroup 无效。";
            if (n.widthGroup !== undefined && !/^[A-Za-z][A-Za-z0-9_-]*$/.test(n.widthGroup)) throw "节点 " + n.id + " 的 widthGroup 无效。";
            if (n.rowSpan !== undefined && (!isFiniteNumber(n.rowSpan) || n.rowSpan < 1 || Math.floor(n.rowSpan) !== n.rowSpan)) throw "节点 " + n.id + " 的 rowSpan 必须是正整数。";
            if (n.columnSpan !== undefined && (!isFiniteNumber(n.columnSpan) || n.columnSpan < 1 || Math.floor(n.columnSpan) !== n.columnSpan)) throw "节点 " + n.id + " 的 columnSpan 必须是正整数。";
            if ((n.rowSpan > 1 || n.columnSpan > 1) && Math.floor(n.column) !== n.column) throw "跨行或跨列节点必须使用整数 column。";
            if (root.schemaVersion < 3 && (n.heightGroup !== undefined || n.widthGroup !== undefined || n.rowSpan !== undefined || n.columnSpan !== undefined || n.shape === "ellipse" || n.shape === "cylinder" || n.shape === "arrow" || n.shape === "brace" || n.shape === "plusCircle" || n.shape === "minusCircle" || n.shape === "label" || n.shape === "functionBlock" || n.shape === "multiplier" || n.shape === "summer" || n.shape === "port" || n.shape === "waveBlock" || n.shape === "sideCurveBlock" || n.shape === "inputOutput" || n.shape === "predefinedProcess")) throw "节点 " + n.id + " 使用了 schemaVersion 3 字段。";
            if (n.shape === "decision") {
                lines = String(n.text).replace(/\r\n|\r/g, "\n").split("\n"); longest = 0;
                for (j = 0; j < lines.length; j++) longest = Math.max(longest, textUnits(lines[j]));
                if (longest > 14) throw "[decision-line] 判断节点 " + n.id + " 的单行文字过长；请按原图或自然短语换行，避免超扁菱形。";
            }
            ids[n.id] = true;
            rowById[n.id] = n.row;
            if (n.shape === "label") textOnlyIds[n.id] = true;
        }
        for (key in ids) if (ids.hasOwnProperty(key)) endpointIds[key] = true;
        validateContainers(root.containers || [], ids, endpointIds, rowById);
        validateSwimlaneLayout(root, ids);
        validateStacks(root.stacks || [], ids);
        validateHorizontalStacks(root.horizontalStacks || [], ids);
        validateFreeTexts(root.freeTexts || []);
        validateFreeLines(root.freeLines || []);
        validateFreeDots(root.freeDots || []);
        for (i = 0; i < root.edges.length; i++) {
            e = root.edges[i];
            if (e && e.id !== undefined) {
                if (!/^[A-Za-z][A-Za-z0-9_-]*$/.test(e.id) || edgeIds[e.id] !== undefined) throw "连接 " + (i + 1) + " 的 id 无效或重复。";
                edgeIds[e.id] = i;
            }
        }
        for (i = 0; i < root.edges.length; i++) {
            e = root.edges[i];
            hasFrom = e && e.from !== undefined; hasFromEdge = e && e.fromEdge !== undefined;
            hasTo = e && e.to !== undefined; hasToEdge = e && e.toEdge !== undefined;
            if (!e || hasFrom === hasFromEdge || hasTo === hasToEdge || (hasFrom && !endpointIds[e.from]) || (hasTo && !endpointIds[e.to])) throw "连接 " + (i + 1) + " 的起点和终点必须各自使用一个节点/容器或一条已命名连接。";
            if ((hasFrom && textOnlyIds[e.from]) || (hasTo && textOnlyIds[e.to])) throw "[text-only-node] 连接不能以 label 文字节点作为端点。";
            if (hasFromEdge && (edgeIds[e.fromEdge] === undefined || edgeIds[e.fromEdge] >= i || e.fromEdgePosition !== "middle")) throw "连接 " + (i + 1) + " 的 fromEdge 必须引用它之前的已命名连接，且 fromEdgePosition 必须为 middle。";
            if (!hasFromEdge && e.fromEdgePosition !== undefined) throw "连接 " + (i + 1) + " 只有使用 fromEdge 时才能设置 fromEdgePosition。";
            if (hasToEdge && (edgeIds[e.toEdge] === undefined || edgeIds[e.toEdge] >= i || e.toEdgePosition !== "middle")) throw "连接 " + (i + 1) + " 的 toEdge 必须引用它之前的已命名连接，且 toEdgePosition 必须为 middle。";
            if (!hasToEdge && e.toEdgePosition !== undefined) throw "连接 " + (i + 1) + " 只有使用 toEdge 时才能设置 toEdgePosition。";
            if (hasFrom && hasTo && e.from === e.to) throw "不支持节点自连：" + e.from;
            if (e.label !== undefined && typeof e.label !== "string") throw "连接 " + (i + 1) + " 的 label 必须是字符串。";
            if ((e.fromPort === undefined) !== (e.toPort === undefined)) throw "连接 " + (i + 1) + " 必须同时设置 fromPort 和 toPort。";
            if (e.fromPort !== undefined && (!ports[e.fromPort] || !ports[e.toPort])) throw "连接 " + (i + 1) + " 的端口无效。";
            if (e.fromPortPosition !== undefined && (!portPositions[e.fromPortPosition] || e.fromPort === undefined)) throw "连接 " + (i + 1) + " 的 fromPortPosition 无效。";
            if (e.toPortPosition !== undefined && (!portPositions[e.toPortPosition] || e.toPort === undefined)) throw "连接 " + (i + 1) + " 的 toPortPosition 无效。";
            if (e.labelPosition !== undefined && !labelPositions[e.labelPosition]) throw "连接 " + (i + 1) + " 的 labelPosition 无效。";
            if (e.arrow !== undefined && !arrows[e.arrow]) throw "连接 " + (i + 1) + " 的 arrow 无效。";
            if (e.via !== undefined) {
                if (!(e.via instanceof Array) || e.via.length === 0) throw "连接 " + (i + 1) + " 的 via 必须是非空数组。";
                if (e.fromPort === undefined) throw "连接 " + (i + 1) + " 使用 via 时必须显式设置端口。";
                if (e.fromPort === e.toPort) throw "[route-reversal] 连接 " + (i + 1) + " 的同侧回路不能使用 via；请改用 routeLane，避免 3 mm 局部腿反向折返。";
                for (j = 0; j < e.via.length; j++) validateVia(e.via[j], i, j);
                if (!keepsSourceAxis(e.via[0])) throw "连接 " + (i + 1) + " 的首个 via 必须保留 from 坐标轴，避免起始段产生斜线。";
                if (!keepsTargetAxis(e.via[e.via.length - 1])) throw "连接 " + (i + 1) + " 的最后 via 必须保留 to 坐标轴，避免末段产生斜线。";
            }
            if (e.labelSegment !== undefined && (!isFiniteNumber(e.labelSegment) || e.labelSegment < 0 || Math.floor(e.labelSegment) !== e.labelSegment)) throw "连接 " + (i + 1) + " 的 labelSegment 必须是非负整数。";
            if (e.labelSide !== undefined && !labelSides[e.labelSide]) throw "连接 " + (i + 1) + " 的 labelSide 无效。";
            if (e.lineStyle !== undefined && !lineStyles[e.lineStyle]) throw "连接 " + (i + 1) + " 的 lineStyle 无效。";
            if (e.routeStyle !== undefined && !routeStyles[e.routeStyle]) throw "连接 " + (i + 1) + " 的 routeStyle 无效。";
            if (e.shaftLength !== undefined && e.shaftLength !== "2mm" && e.shaftLength !== "3mm") throw "连接 " + (i + 1) + " 的 shaftLength 无效。";
            if (e.routeLane !== undefined && (!isFiniteNumber(e.routeLane) || e.routeLane < 1 || Math.floor(e.routeLane) !== e.routeLane || e.fromPort === undefined || e.fromPort !== e.toPort || e.via !== undefined)) throw "连接 " + (i + 1) + " 的 routeLane 只能是无 via 同侧回路的正整数。";
            if (e.routeStyle === "straight" && root.kind !== "blockDiagram" && root.kind !== "signalFlow") throw "连接 " + (i + 1) + " 只有 blockDiagram 或 signalFlow 可以使用 straight 路线。";
            if (e.routeStyle === "straight" && e.fromPort === undefined) throw "连接 " + (i + 1) + " 使用 straight 时必须显式设置端口。";
            if (e.routeStyle === "straight" && e.via !== undefined) throw "连接 " + (i + 1) + " 不能同时使用 straight 和 via。";
            if ((hasFromEdge || hasToEdge) && (e.routeStyle === "straight" || e.via !== undefined)) throw "连接 " + (i + 1) + " 与其他连接衔接时只能使用自动正交路线。";
            if (root.schemaVersion === 1 && (e.fromPort !== undefined || e.labelPosition !== undefined)) throw "连接 " + (i + 1) + " 使用了 schemaVersion 2 字段。";
            if (root.schemaVersion < 3 && (e.id !== undefined || e.fromEdge !== undefined || e.fromEdgePosition !== undefined || e.toEdge !== undefined || e.toEdgePosition !== undefined || e.arrow !== undefined || e.via !== undefined || e.labelSegment !== undefined || e.labelSide !== undefined || e.lineStyle !== undefined || e.routeStyle !== undefined || e.fromPortPosition !== undefined || e.toPortPosition !== undefined || e.shaftLength !== undefined || e.routeLane !== undefined)) throw "连接 " + (i + 1) + " 使用了 schemaVersion 3 字段。";
            if (hasFrom && hasTo) directed[e.from + ">" + e.to] = e;
        }
        validateStackBranchCrossings(root);
        validateNativeCombBusPorts(root);
        for (i = 0; i < root.edges.length; i++) {
            e = root.edges[i];
            if (e.fromEdge !== undefined || e.toEdge !== undefined) continue;
            key = e.from < e.to ? e.from + "<>" + e.to : e.to + "<>" + e.from;
            if (checked[key]) continue;
            checked[key] = true; reverse = directed[e.to + ">" + e.from];
            if (!reverse) continue;
            separated = (e.fromPort !== undefined && e.fromPort === e.toPort) ||
                        (reverse.fromPort !== undefined && reverse.fromPort === reverse.toPort) ||
                        e.via !== undefined || reverse.via !== undefined;
            if (!separated) throw "[reciprocal] 互反连接 " + e.from + "<->" + e.to + " 会重合；至少一条边必须使用同侧显式端口形成外绕回环。";
        }
        if (looksLikeModuleTree(root)) throw "[module-tree-config] 该图是单根、多模块、末级竖排子项的模块树；必须设置 treeLayout: \"module\"，不要让普通网格布局处理。";
        if (root.treeLayout === "module") validateModuleTree(root);
    }

    function validateModuleTree(root) {
        if (root.layoutMode !== "compact") throw "[module-tree] 模块树必须使用 layoutMode: compact。";
        if (root.fontSize !== 8) throw "[module-tree] 模块树必须显式使用固定 8 pt 字号。";
        if (root.flowShapePolicy !== "sourceVisible") throw "[module-tree] 模块树必须使用 flowShapePolicy: sourceVisible，避免自动替换端点形状。";

        var byId = {}, outgoing = {}, incoming = {}, children = {}, leaves = [], branches = [], roots = [];
        var leafHeightGroup = null, leafWidthGroup = null, leafRow = null, branchHeightGroup = null, branchRow = null;
        var minLeafColumn = null, maxLeafColumn = null, i, j, n, e, child, allLeaves, minColumn, maxColumn, expectedColumn;
        for (i = 0; i < root.nodes.length; i++) {
            n = root.nodes[i];
            byId[n.id] = n;
            outgoing[n.id] = 0;
            incoming[n.id] = 0;
            children[n.id] = [];
        }
        for (i = 0; i < root.edges.length; i++) {
            e = root.edges[i];
            if (e.fromEdge !== undefined || e.toEdge !== undefined) throw "[module-tree] 模块树只允许节点到节点的直接连接。";
            if (e.arrow !== "none") throw "[module-tree] 模块树连接必须显式设置 arrow: none。";
            outgoing[e.from] += 1;
            incoming[e.to] += 1;
            children[e.from].push(e.to);
        }
        for (i = 0; i < root.nodes.length; i++) {
            n = root.nodes[i];
            if (incoming[n.id] === 0) roots.push(n);
            if (outgoing[n.id] === 0) {
                if (n.textDirection !== "vertical") throw "[module-tree] 叶节点 " + n.id + " 必须使用 vertical 文字。";
                if (!n.heightGroup) throw "[module-tree] 叶节点 " + n.id + " 必须设置公共 heightGroup。";
                if (!n.widthGroup) throw "[module-tree] 叶节点 " + n.id + " 必须设置公共 widthGroup。";
                if (leafHeightGroup === null) leafHeightGroup = n.heightGroup;
                else if (leafHeightGroup !== n.heightGroup) throw "[module-tree] 所有叶节点必须共享同一个 heightGroup。";
                if (leafWidthGroup === null) leafWidthGroup = n.widthGroup;
                else if (leafWidthGroup !== n.widthGroup) throw "[module-tree] 所有叶节点必须共享同一个 widthGroup。";
                if (leafRow === null) leafRow = n.row;
                else if (leafRow !== n.row) throw "[module-tree] 所有叶节点必须位于同一终端行。";
                minLeafColumn = minLeafColumn === null ? n.column : Math.min(minLeafColumn, n.column);
                maxLeafColumn = maxLeafColumn === null ? n.column : Math.max(maxLeafColumn, n.column);
                leaves.push(n);
            } else if (incoming[n.id] > 0) {
                if (!n.heightGroup) throw "[module-tree] 模块标题 " + n.id + " 必须设置公共 heightGroup。";
                if (branchHeightGroup === null) branchHeightGroup = n.heightGroup;
                else if (branchHeightGroup !== n.heightGroup) throw "[module-tree] 同层模块标题必须共享同一个 heightGroup。";
                if (branchRow === null) branchRow = n.row;
                else if (branchRow !== n.row) throw "[module-tree] 模块标题必须位于同一行。";
                branches.push(n);
            }
        }
        if (!leaves.length) throw "[module-tree] 模块树至少需要一个叶节点。";
        if (roots.length !== 1) throw "[module-tree] 模块树必须且只能有一个根节点。";
        expectedColumn = (minLeafColumn + maxLeafColumn) / 2;
        if (roots[0].column !== expectedColumn) throw "[module-tree] 根节点必须位于全部叶节点跨度的中心 column " + expectedColumn + "。";

        var leafGroups = [];
        for (i = 0; i < branches.length; i++) {
            n = branches[i];
            allLeaves = children[n.id].length > 0;
            minColumn = null;
            maxColumn = null;
            for (j = 0; j < children[n.id].length; j++) {
                child = byId[children[n.id][j]];
                if (outgoing[child.id] !== 0) allLeaves = false;
                minColumn = minColumn === null ? child.column : Math.min(minColumn, child.column);
                maxColumn = maxColumn === null ? child.column : Math.max(maxColumn, child.column);
            }
            if (!allLeaves) throw "[module-tree] 模块标题 " + n.id + " 的直接子项必须全部是叶节点。";
            expectedColumn = (minColumn + maxColumn) / 2;
            if (n.column !== expectedColumn) throw "[module-tree] 模块标题 " + n.id + " 必须位于子项跨度的中心 column " + expectedColumn + "。";
            leafGroups.push({ min: minColumn, max: maxColumn, id: n.id });
        }
        leafGroups.sort(function (a, b) { return a.min - b.min; });
    }

    function looksLikeModuleTree(root) {
        if (root.kind !== "flowchart" || root.treeLayout === "module" || root.nodes.length < 7) return false;
        var byId = {}, incoming = {}, outgoing = {}, roots = [], leaves = [], branches = [], i, j, n, edge, child;
        for (i = 0; i < root.nodes.length; i++) {
            n = root.nodes[i]; byId[n.id] = n; incoming[n.id] = 0; outgoing[n.id] = [];
        }
        for (i = 0; i < root.edges.length; i++) {
            edge = root.edges[i];
            if (edge.from === undefined || edge.to === undefined || !byId[edge.from] || !byId[edge.to]) continue;
            incoming[edge.to] += 1; outgoing[edge.from].push(edge.to);
        }
        for (i = 0; i < root.nodes.length; i++) {
            n = root.nodes[i];
            if (incoming[n.id] === 0) roots.push(n);
            else if (outgoing[n.id].length === 0) leaves.push(n);
            else branches.push(n);
        }
        if (roots.length !== 1 || branches.length < 2 || leaves.length < 4) return false;
        for (i = 0; i < branches.length; i++) if (outgoing[branches[i].id].length < 2) return false;
        for (i = 0; i < branches.length; i++) {
            n = branches[i];
            if (n.row !== branches[0].row) return false;
            for (j = 0; j < outgoing[n.id].length; j++) {
                child = byId[outgoing[n.id][j]];
                if (!child || outgoing[child.id].length !== 0) return false;
            }
        }
        for (i = 0; i < leaves.length; i++) if (leaves[i].textDirection !== "vertical" || leaves[i].row !== leaves[0].row) return false;
        if (outgoing[roots[0].id].length !== branches.length) return false;
        for (i = 0; i < branches.length; i++) if (outgoing[roots[0].id].indexOf(branches[i].id) < 0) return false;
        return true;
    }

    function validateVia(point, edgeIndex, pointIndex) {
        if (!point || typeof point !== "object") throw "连接 " + (edgeIndex + 1) + " 的 via[" + pointIndex + "] 无效。";
        if (!validAxis(point.x) || !validAxis(point.y)) throw "连接 " + (edgeIndex + 1) + " 的 via[" + pointIndex + "] 坐标无效。";
    }

    function validAxis(value) {
        return value === "from" || value === "to" || value === "from+gap" || value === "from-gap" ||
               value === "to+gap" || value === "to-gap" ||
               (isFiniteNumber(value) && Math.round(value * 2) === value * 2);
    }

    function keepsSourceAxis(point) { return sourceAxis(point.x) || sourceAxis(point.y); }
    function keepsTargetAxis(point) { return targetAxis(point.x) || targetAxis(point.y); }
    function sourceAxis(value) { return value === "from" || value === "from+gap" || value === "from-gap"; }
    function targetAxis(value) { return value === "to" || value === "to+gap" || value === "to-gap"; }

    function validateContainers(containers, ids, endpointIds, rowById) {
        var seen = {}, rows = {}, rowCount, rowKey, i, j, item;
        for (i = 0; i < containers.length; i++) {
            item = containers[i];
            if (!item || !/^[A-Za-z][A-Za-z0-9_-]*$/.test(item.id || "")) throw "容器 " + (i + 1) + " 的 id 无效。";
            if (seen[item.id] || ids[item.id]) throw "容器 id 重复或与节点冲突：" + item.id;
            if (!(item.members instanceof Array) || item.members.length === 0) throw "容器 " + item.id + " 的 members 必须是非空数组。";
            if (item.padding !== undefined && item.padding !== "minimal" && item.padding !== "tight" && item.padding !== "normal") throw "容器 " + item.id + " 的 padding 无效。";
            if (item.sizeClass !== undefined && item.sizeClass !== "wideNested") throw "容器 " + item.id + " 的 sizeClass 无效。";
            if (item.sizeClass === "wideNested" && item.members.length !== 1) throw "wideNested 容器必须只有一个成员。";
            if (item.lineStyle !== undefined && item.lineStyle !== "solid" && item.lineStyle !== "dashed" && item.lineStyle !== "dotted") throw "容器 " + item.id + " 的 lineStyle 无效。";
            if (item.cornerStyle !== undefined && item.cornerStyle !== "square" && item.cornerStyle !== "rounded") throw "容器 " + item.id + " 的 cornerStyle 无效。";
            if (item.label !== undefined && (typeof item.label !== "string" || item.label === "")) throw "容器 " + item.id + " 的 label 无效。";
            if (item.labelPosition !== undefined && item.labelPosition !== "topCenter" && item.labelPosition !== "bottomRight") throw "容器 " + item.id + " 的 labelPosition 无效。";
            if (item.frameGroup !== undefined && !/^[A-Za-z][A-Za-z0-9_-]*$/.test(item.frameGroup)) throw "容器 " + item.id + " 的 frameGroup 无效。";
            if (item.memberDistribution !== undefined && item.memberDistribution !== "spaceBetween" && item.memberDistribution !== "compact") throw "容器 " + item.id + " 的 memberDistribution 无效。";
            for (j = 0; j < item.members.length; j++) if (!ids[item.members[j]]) throw "容器 " + item.id + " 引用了不存在的节点。";
            if (item.memberDistribution === "spaceBetween" || item.memberDistribution === "compact") {
                rows = {};
                for (j = 0; j < item.members.length; j++) rows[rowById[item.members[j]]] = true;
                rowCount = 0;
                for (rowKey in rows) if (rows.hasOwnProperty(rowKey)) rowCount++;
                if (rowCount > 1) throw "[member-distribution-row] 容器 " + item.id + " 的 spaceBetween 只能用于同一 row 的单行成员；多行模块或设备+说明组合必须省略该字段。";
            }
            seen[item.id] = true; endpointIds[item.id] = true;
        }
    }

    function validateSwimlaneLayout(root, ids) {
        if (root.swimlaneLayout === undefined) return;
        if (!(root.containers instanceof Array) || root.containers.length < 2) throw "[swimlane-count] 共享泳道至少需要两个 containers。";
        var owners = {}, i, j, lane, member, id, style;
        for (i = 0; i < root.containers.length; i++) {
            lane = root.containers[i];
            if (typeof lane.label !== "string" || lane.label === "") throw "[swimlane-title] 泳道 " + lane.id + " 必须有非空 label。";
            if (lane.labelDirection !== undefined && lane.labelDirection !== "horizontal" && lane.labelDirection !== "vertical") throw "[swimlane-title] 泳道 " + lane.id + " 的 labelDirection 无效。";
            if (lane.cornerStyle !== undefined && lane.cornerStyle !== "square") throw "[swimlane-frame] 泳道 " + lane.id + " 必须使用直角边框。";
            if (lane.memberDistribution !== undefined || lane.frameGroup !== undefined || lane.labelPosition !== undefined) throw "[swimlane-frame] 泳道 " + lane.id + " 不能使用普通容器的分布、框组或标题位置。";
            style = style || lane.lineStyle || "solid";
            if ((lane.lineStyle || "solid") !== style) throw "[swimlane-frame] 共享泳道的 lineStyle 必须一致。";
            for (j = 0; j < lane.members.length; j++) {
                member = lane.members[j];
                if (owners[member]) throw "[swimlane-member] 节点 " + member + " 不能同时属于泳道 " + owners[member] + " 和 " + lane.id + "。";
                owners[member] = lane.id;
            }
        }
        for (id in ids) if (ids.hasOwnProperty(id) && !owners[id]) throw "[swimlane-member] 节点 " + id + " 未归属任何泳道。";
    }

    function validateStacks(stacks, ids) {
        var seenIds = {}, seenMembers = {}, i, j, item, member;
        for (i = 0; i < stacks.length; i++) {
            item = stacks[i];
            if (!item || !/^[A-Za-z][A-Za-z0-9_-]*$/.test(item.id || "")) throw "纵向栈 " + (i + 1) + " 的 id 无效。";
            if (seenIds[item.id]) throw "纵向栈 id 重复：" + item.id;
            if (!(item.members instanceof Array) || item.members.length < 2) throw "纵向栈 " + item.id + " 至少需要两个成员。";
            if (item.gap !== undefined && item.gap !== "minimal" && item.gap !== "standard") throw "纵向栈 " + item.id + " 的 gap 无效。";
            for (j = 0; j < item.members.length; j++) {
                member = item.members[j];
                if (!ids[member]) throw "纵向栈 " + item.id + " 引用了不存在的节点。";
                if (seenMembers[member]) throw "节点 " + member + " 不能同时属于多个纵向栈。";
                seenMembers[member] = true;
            }
            seenIds[item.id] = true;
        }
    }

    function validateHorizontalStacks(stacks, ids) {
        var seenIds = {}, seenMembers = {}, i, j, item, member;
        for (i = 0; i < stacks.length; i++) {
            item = stacks[i];
            if (!item || !/^[A-Za-z][A-Za-z0-9_-]*$/.test(item.id || "")) throw "水平栈 " + (i + 1) + " 的 id 无效。";
            if (seenIds[item.id]) throw "水平栈 id 重复：" + item.id;
            if (!(item.members instanceof Array) || item.members.length < 2) throw "水平栈 " + item.id + " 至少需要两个成员。";
            for (j = 0; j < item.members.length; j++) {
                member = item.members[j];
                if (!ids[member]) throw "水平栈 " + item.id + " 引用了不存在的节点。";
                if (seenMembers[member]) throw "节点 " + member + " 不能同时属于多个水平栈。";
                seenMembers[member] = true;
            }
            seenIds[item.id] = true;
        }
    }

    function validateStackBranchCrossings(root) {
        var byId = {}, direct = {}, i, j, k, stack, source, target, node, bridges;
        if (!(root.stacks instanceof Array) || root.stacks.length === 0) return;
        for (i = 0; i < root.nodes.length; i++) byId[root.nodes[i].id] = root.nodes[i];
        for (i = 0; i < root.edges.length; i++) {
            if (root.edges[i] && root.edges[i].from !== undefined && root.edges[i].to !== undefined) direct[root.edges[i].from + "\u0000" + root.edges[i].to] = true;
        }
        for (i = 0; i < root.stacks.length; i++) {
            stack = root.stacks[i];
            for (j = 1; j < stack.members.length; j++) {
                source = byId[stack.members[j - 1]]; target = byId[stack.members[j]];
                if (target.row <= source.row + 1) continue;
                bridges = [];
                for (k = 0; k < root.nodes.length; k++) {
                    node = root.nodes[k];
                    if (node.row > source.row && node.row < target.row && direct[source.id + "\u0000" + node.id] && direct[node.id + "\u0000" + target.id]) bridges.push(node.id);
                }
                if (bridges.length) throw "[stack-branch-crossing] 纵向栈 " + stack.id + " 的 " + source.id + " -> " + target.id + " 跨过分支层 " + bridges.join(", ") + "；请拆分或移除该 stack，保留网格行的分流与汇流顺序。";
            }
        }
    }

    function validateNativeCombBusPorts(root) {
        var byId = {}, outgoing = {}, incoming = {}, i, j, edge, source, target, entries, adjacent, node, key;
        for (i = 0; i < root.nodes.length; i++) byId[root.nodes[i].id] = root.nodes[i];
        for (i = 0; i < root.edges.length; i++) {
            edge = root.edges[i];
            if (edge.from === undefined || edge.to === undefined) continue;
            if (!outgoing[edge.from]) outgoing[edge.from] = [];
            if (!incoming[edge.to]) incoming[edge.to] = [];
            outgoing[edge.from].push(edge); incoming[edge.to].push(edge);
        }
        for (key in outgoing) {
            if (!outgoing.hasOwnProperty(key)) continue;
            source = byId[key];
            if (!source) continue;
            entries = outgoing[key]; adjacent = [];
            for (i = 0; i < entries.length; i++) {
                node = byId[entries[i].to];
                if (node && node.row === source.row + 1) adjacent.push(entries[i]);
            }
            if (adjacent.length < 3) continue;
            for (i = 0; i < adjacent.length; i++) if (adjacent[i].fromPort !== undefined) throw "[native-comb-bus] 节点 " + key + " 的同排多路分流必须省略显式端口，以使用 2 mm 梳状母线和 1 mm 紧凑框距。";
        }
        for (key in incoming) {
            if (!incoming.hasOwnProperty(key)) continue;
            target = byId[key];
            if (!target) continue;
            entries = incoming[key]; adjacent = [];
            for (j = 0; j < entries.length; j++) {
                node = byId[entries[j].from];
                if (node && node.row + 1 === target.row) adjacent.push(entries[j]);
            }
            if (adjacent.length < 3) continue;
            for (j = 0; j < adjacent.length; j++) if (adjacent[j].fromPort !== undefined) throw "[native-comb-bus] 节点 " + key + " 的同排多路汇流必须省略显式端口，以使用 2 mm 梳状母线和 1 mm 紧凑框距。";
        }
    }

    function validateFreeTexts(items) {
        var i, it;
        for (i = 0; i < items.length; i++) {
            it = items[i];
            if (!it || typeof it.t !== "string") throw "freeTexts[" + i + "] 缺少 t。";
            if (!isFiniteNumber(it.xr) || it.xr < 0 || it.xr > 1 || !isFiniteNumber(it.yr) || it.yr < 0 || it.yr > 1) throw "freeTexts[" + i + "] 的 xr/yr 必须在 0..1。";
            if (it.align !== undefined && it.align !== "left" && it.align !== "center" && it.align !== "right") throw "freeTexts[" + i + "] 的 align 无效。";
        }
    }

    function validUnitPoint(it) {
        return isFiniteNumber(it.x1) && it.x1 >= 0 && it.x1 <= 1 && isFiniteNumber(it.y1) && it.y1 >= 0 && it.y1 <= 1 && isFiniteNumber(it.x2) && it.x2 >= 0 && it.x2 <= 1 && isFiniteNumber(it.y2) && it.y2 >= 0 && it.y2 <= 1;
    }

    function validateFreeLines(items) {
        var i, it;
        for (i = 0; i < items.length; i++) {
            it = items[i];
            if (!it || !validUnitPoint(it)) throw "freeLines[" + i + "] 的 x1/y1/x2/y2 必须在 0..1。";
            if (it.arrow !== undefined && it.arrow !== "none" && it.arrow !== "start" && it.arrow !== "end" && it.arrow !== "both") throw "freeLines[" + i + "] 的 arrow 无效。";
            if (it.lineStyle !== undefined && it.lineStyle !== "solid" && it.lineStyle !== "dashed" && it.lineStyle !== "dotted") throw "freeLines[" + i + "] 的 lineStyle 无效。";
        }
    }

    function validateFreeDots(items) {
        var i, it;
        for (i = 0; i < items.length; i++) {
            it = items[i];
            if (!it || !validUnitPoint(it)) throw "freeDots[" + i + "] 的 x1/y1/x2/y2 必须在 0..1。";
            if (it.count !== undefined && (!isFiniteNumber(it.count) || it.count < 2 || Math.floor(it.count) !== it.count)) throw "freeDots[" + i + "] 的 count 必须是大于 1 的整数。";
            if (it.radius !== undefined && (!isFiniteNumber(it.radius) || it.radius <= 0)) throw "freeDots[" + i + "] 的 radius 必须是正数。";
        }
    }

    function assertNodeSeparation(nodes){
        for(var i=0;i<nodes.length;i++)for(var j=i+1;j<nodes.length;j++){
            var a=nodes[i],b=nodes[j];if(a.shape==='port'||b.shape==='port'||a.shape==='label'||b.shape==='label')continue;
            if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>.25&&Math.min(a.top,b.top)-Math.max(a.bottom,b.bottom)>.25)throw Error('LAYOUT_REFLOW_REQUIRED: overlapping nodes '+a.id+' / '+b.id);
        }
    }

    function chooseLayout(data, maxW, maxH, font) {
        var i, layout, fallback;
        if (data.nodes.length === 0) return freeformLayout(data, maxW, maxH);
        if (data.fontSize !== undefined) return measureLayout(data, data.fontSize, font);
        for (i = 0; i < CFG.FONT_SIZES.length; i++) {
            layout = measureLayout(data, CFG.FONT_SIZES[i], font);
            fallback = layout;
            if (layout.width <= maxW && layout.height <= maxH) return layout;
        }
        return fallback;
    }

    function freeformLayout(data, maxW, maxH) {
        var ratio = data.ratio && data.ratio > 0 ? data.ratio : 0.66;
        return { nodes: [], byId: {}, containerSpecs: [], containers: [], stackSpecs: [], horizontalStackSpecs: [], edges: [], colCenters: [], rowCenters: [], colStarts: [], rowStarts: [], colW: [], rowH: [], rowGaps: [], columnGaps: [], containerMargin: 0, sideLabelWidth: 0, width: maxW, height: Math.min(maxH, maxW * ratio), fontSize: 8 };
    }

    function moduleTreeLayoutData(data) {
        var byId = {}, incoming = {}, outgoing = {}, branches = [], root = null, i, j, n, edge, child, branch, children, minColumn, mappedColumn = 0, mapped = {}, result = [], copy, key;
        for (i = 0; i < data.nodes.length; i++) {
            n = data.nodes[i]; byId[n.id] = n; incoming[n.id] = 0; outgoing[n.id] = [];
        }
        for (i = 0; i < data.edges.length; i++) {
            edge = data.edges[i];
            if (edge.from === undefined || edge.to === undefined || !byId[edge.from] || !byId[edge.to]) continue;
            incoming[edge.to] += 1; outgoing[edge.from].push(edge.to);
        }
        for (i = 0; i < data.nodes.length; i++) {
            n = data.nodes[i];
            if (incoming[n.id] === 0) root = n;
            else if (outgoing[n.id].length > 0) branches.push(n);
        }
        branches.sort(function (a, b) {
            var amin = 999999, bmin = 999999, k, c;
            for (k = 0; k < outgoing[a.id].length; k++) { c = byId[outgoing[a.id][k]]; amin = Math.min(amin, c.column); }
            for (k = 0; k < outgoing[b.id].length; k++) { c = byId[outgoing[b.id][k]]; bmin = Math.min(bmin, c.column); }
            return amin - bmin;
        });
        for (i = 0; i < branches.length; i++) {
            branch = branches[i]; children = [];
            for (j = 0; j < outgoing[branch.id].length; j++) children.push(byId[outgoing[branch.id][j]]);
            children.sort(function (a, b) { return a.column - b.column; });
            minColumn = mappedColumn;
            for (j = 0; j < children.length; j++) {
                copy = {}; for (key in children[j]) if (children[j].hasOwnProperty(key)) copy[key] = children[j][key];
                copy.column = mappedColumn; mapped[copy.id] = copy; mappedColumn += 1;
            }
            copy = {}; for (key in branch) if (branch.hasOwnProperty(key)) copy[key] = branch[key];
            copy.column = (minColumn + mappedColumn - 1) / 2; mapped[copy.id] = copy;
        }
        if (root) {
            copy = {}; for (key in root) if (root.hasOwnProperty(key)) copy[key] = root[key];
            copy.column = (mappedColumn - 1) / 2; mapped[copy.id] = copy;
        }
        for (i = 0; i < data.nodes.length; i++) result.push(mapped[data.nodes[i].id] || data.nodes[i]);
        return { nodes: result, edges: data.edges, layoutMode: "compact", containers: [], stacks: [], horizontalStacks: [] };
    }

    function measureLayout(data, fontSize, font) {
        if (data.treeLayout === "module") return measureLayout(moduleTreeLayoutData(data), fontSize, font);
        var sourceNodes = data.nodes, edges = data.edges, containers = data.containers || [], stacks = data.stacks || [], horizontalStacks = data.horizontalStacks || [];
        for (var ci = 0; ci < containers.length; ci++) {
            if (!containers[ci].label || data.swimlaneLayout || containers[ci].sizeClass) continue;
            var titleMeasure = measureContainerTitle(displayText(containers[ci].label, false), fontSize, font);
            containers[ci].titleWidth = titleMeasure.w; containers[ci].titleHeight = titleMeasure.h; containers[ci].titleGap = 3 * fontSize / 8;
        }
        var columnGap = data.layoutMode === "compact" ? CFG.COLUMN_GAP_COMPACT : CFG.COLUMN_GAP_STANDARD;
        var nodes = [], byId = {}, maxRow = 0, maxCol = 0, i, n, text, measure, size, rowSpan, columnSpan;
        for (i = 0; i < sourceNodes.length; i++) {
            n = sourceNodes[i];
            text = displayText(n.text, n.textDirection === "vertical");
            measure = measureText(text, fontSize, font);
            size = calibratedBoxSize(n, measure, fontSize);
            rowSpan = n.rowSpan || 1; columnSpan = n.columnSpan || 1;
            var item = {
                source: n, id: n.id, text: text, row: n.row, column: n.column, shape: n.shape,
                w: size.w, h: size.h, rowSpan: rowSpan, columnSpan: columnSpan,
                heightGroup: n.heightGroup, widthGroup: n.widthGroup,
                arrowDirection: n.arrowDirection, arrowHeads: n.arrowHeads, arrowLabelSide: n.arrowLabelSide, braceSide: n.braceSide
            };
            nodes.push(item); byId[n.id] = item;
            if (n.row + rowSpan - 1 > maxRow) maxRow = n.row + rowSpan - 1;
            if (n.column + columnSpan - 1 > maxCol) maxCol = n.column + columnSpan - 1;
        }

        equalizeHeightGroups(nodes);
        equalizeWidthGroups(nodes);
        applyContainerSizeClasses(containers, byId);

        var colCount = Math.ceil(maxCol) + 1, colW = [], rowH = [], c, r;
        for (c = 0; c < colCount; c++) colW[c] = 0;
        for (r = 0; r <= maxRow; r++) rowH[r] = 0;
        for (i = 0; i < nodes.length; i++) {
            n = nodes[i];
            if (n.columnSpan === 1 && Math.floor(n.column) === n.column) colW[n.column] = Math.max(colW[n.column], n.w);
            else if (n.columnSpan === 1) {
                c = Math.floor(n.column);
                var share = Math.max(0, (n.w - columnGap) / 2);
                colW[c] = Math.max(colW[c], share);
                if (c + 1 < colCount) colW[c + 1] = Math.max(colW[c + 1], share);
            }
            if (n.rowSpan === 1) rowH[n.row] = Math.max(rowH[n.row], n.h + (n.shape === "arrow" && n.text ? 2 * (measureText(n.text, fontSize, font).h + 3 * fontSize / 8) : 0));
        }
        for (c = 0; c < colCount; c++) if (colW[c] === 0) colW[c] = 1;
        for (r = 0; r <= maxRow; r++) if (rowH[r] === 0) rowH[r] = CFG.HORIZONTAL_BOX_HEIGHT * fontSize / 8;

        var rowGaps = containerAwareRowGaps(nodes, data.swimlaneLayout ? [] : containers, edges, branchAwareRowGaps(nodes, edges, maxRow));
        var columnGaps = columnTrackGaps(nodes, byId, edges, colCount, columnGap);
        distributeSpanDeficits(nodes, colW, rowH, columnGaps, rowGaps);
        reserveSameRowSpacing(nodes, colW, columnGaps);

        var gridWidth = 0, width, height = 0, colCenters = [], rowCenters = [], colStarts = [], rowStarts = [];
        for (c = 0; c < colCount; c++) gridWidth += colW[c];
        for (c = 0; c < columnGaps.length; c++) gridWidth += columnGaps[c];
        width = gridWidth;
        for (i = 0; i < nodes.length; i++) width = Math.max(width, nodes[i].w);
        for (r = 0; r <= maxRow; r++) height += rowH[r];
        for (r = 0; r < maxRow; r++) height += rowGaps[r];

        var containerMargin = containers.length ? maxContainerPadding(containers) : 0;
        var sideLabelWidth = data.sideLabelBand === "layerLabels" ? CFG.LAYER_LABEL_BAND : 0;
        var contentWidth = width;
        width = contentWidth + containerMargin * 2 + sideLabelWidth; height += containerMargin * 2;
        var x = (contentWidth - gridWidth) / 2, y = 0;
        for (c = 0; c < colCount; c++) {
            colStarts[c] = x; colCenters[c] = x + colW[c] / 2; x += colW[c] + (c < columnGaps.length ? columnGaps[c] : 0);
        }
        for (r = 0; r <= maxRow; r++) {
            rowStarts[r] = y; rowCenters[r] = y + rowH[r] / 2; y += rowH[r] + (r < maxRow ? rowGaps[r] : 0);
        }
        var layout = {
            nodes: nodes, byId: byId, containerSpecs: containers, containers: [], swimlaneLayout: data.swimlaneLayout, stackSpecs: stacks, horizontalStackSpecs: horizontalStacks, edges: edges,
            colCenters: colCenters, rowCenters: rowCenters, colStarts: colStarts, rowStarts: rowStarts,
            colW: colW, rowH: rowH, rowGaps: rowGaps, columnGaps: columnGaps, containerMargin: containerMargin,
            width: width, height: height, fontSize: fontSize, sideLabelWidth: sideLabelWidth
        };
        if (stacks.length) layout.height = estimateStackedHeight(layout) + containerMargin * 2;
        return layout;
    }

    function reserveSameRowSpacing(nodes, widths, gaps) {
        function center(column) {
            var c = Math.floor(column), x = 0;
            for (var k = 0; k < c; k++) x += widths[k] + gaps[k];
            x += widths[c] / 2;
            if (column !== c) x += widths[c] / 4 + gaps[c] / 2 + widths[c + 1] / 4;
            return x;
        }
        for (var i = 0; i < nodes.length; i++) for (var j = i + 1; j < nodes.length; j++) {
            var a = nodes[i], b = nodes[j];
            if (a.row !== b.row || a.column === b.column || a.columnSpan !== 1 || b.columnSpan !== 1) continue;
            if (a.column > b.column) { var swap = a; a = b; b = swap; }
            var deficit = (a.w + b.w) / 2 + 3 - (center(b.column) - center(a.column));
            if (deficit > 0) {
                var track = Math.floor(a.column), coefficient = Math.min(b.column, track + 1) - a.column;
                if (coefficient > 0) gaps[track] += deficit / coefficient;
            }
        }
    }

    function estimateStackedHeight(layout) {
        var positions = {}, i, j, n, center, spanH, previous, current, top, bottom, gap;
        for (i = 0; i < layout.nodes.length; i++) {
            n = layout.nodes[i];
            if (n.rowSpan > 1) {
                spanH = trackSpanSize(layout.rowH, n.row, n.rowSpan, layout.rowGaps);
                center = layout.rowStarts[n.row] + spanH / 2;
            } else center = layout.rowCenters[n.row];
            positions[n.id] = { top: center - n.h / 2, bottom: center + n.h / 2, h: n.h };
        }
        for (i = 0; i < layout.stackSpecs.length; i++) {
            gap = layout.stackSpecs[i].gap === "minimal" ? CFG.GAP_MINIMAL : CFG.GAP;
            previous = positions[layout.stackSpecs[i].members[0]];
            for (j = 1; j < layout.stackSpecs[i].members.length; j++) {
                current = positions[layout.stackSpecs[i].members[j]];
                current.top = previous.bottom + gap; current.bottom = current.top + current.h;
                previous = current;
            }
        }
        top = positions[layout.nodes[0].id].top; bottom = positions[layout.nodes[0].id].bottom;
        for (i = 1; i < layout.nodes.length; i++) {
            current = positions[layout.nodes[i].id]; top = Math.min(top, current.top); bottom = Math.max(bottom, current.bottom);
        }
        return bottom - top;
    }

    function equalizeHeightGroups(nodes) {
        var maximums = {}, i, group;
        for (i = 0; i < nodes.length; i++) {
            group = nodes[i].heightGroup;
            if (group) maximums[group] = Math.max(maximums[group] || 0, nodes[i].h);
        }
        for (i = 0; i < nodes.length; i++) {
            group = nodes[i].heightGroup;
            if (group) nodes[i].h = maximums[group];
        }
    }

    function equalizeWidthGroups(nodes) {
        var maximums = {}, i, group;
        for (i = 0; i < nodes.length; i++) {
            group = nodes[i].widthGroup;
            if (group) maximums[group] = Math.max(maximums[group] || 0, nodes[i].w);
        }
        for (i = 0; i < nodes.length; i++) {
            group = nodes[i].widthGroup;
            if (group) nodes[i].w = maximums[group];
        }
    }

    function trackSpanSize(sizes, start, span, gap) {
        var total = 0, i;
        for (i = 0; i < span; i++) {
            total += sizes[start + i];
            if (i < span - 1) total += gap instanceof Array ? gap[start + i] : gap;
        }
        return total;
    }

    function distributeSpanDeficits(nodes, colW, rowH, columnGaps, rowGaps) {
        var i, n, current, deficit, share, c;
        for (i = 0; i < nodes.length; i++) {
            n = nodes[i];
            if (n.columnSpan > 1) {
                current = trackSpanSize(colW, n.column, n.columnSpan, columnGaps);
                if (n.w > current) {
                    share = (n.w - current) / n.columnSpan;
                    for (c = 0; c < n.columnSpan; c++) colW[n.column + c] += share;
                }
            }
            if (n.rowSpan > 1) {
                current = trackSpanSize(rowH, n.row, n.rowSpan, rowGaps);
                if (n.h > current) {
                    deficit = (n.h - current) / n.rowSpan;
                    for (c = 0; c < n.rowSpan; c++) rowH[n.row + c] += deficit;
                }
            }
        }
    }

    function columnTrackGaps(nodes, byId, edges, colCount, baseGap) {
        var gaps = [], i, edge, source, target, fromPort, toPort, start, end, c;
        for (c = 0; c < colCount - 1; c++) gaps[c] = baseGap;
        for (i = 0; i < edges.length; i++) {
            edge = edges[i]; source = byId[edge.from]; target = byId[edge.to];
            if (!source || !target) continue;
            fromPort = edge.fromPort; toPort = edge.toPort;
            if (!fromPort && source.row === target.row) {
                fromPort = target.column > source.column ? "right" : "left";
                toPort = target.column > source.column ? "left" : "right";
            }
            if (!((fromPort === "right" && toPort === "left") || (fromPort === "left" && toPort === "right"))) continue;
            start = Math.floor(Math.min(source.column, target.column)); end = Math.ceil(Math.max(source.column, target.column));
            var requiredGap = shaftRouteGap(edge), j, axis;
            if (edge.via) {
                for (j = 0; j < edge.via.length; j++) {
                    axis = edge.via[j].x;
                    if (axis === "from+gap" || axis === "from-gap" || axis === "to+gap" || axis === "to-gap") requiredGap = CFG.GAP * 2;
                }
            }
            for (c = start; c < end && c < gaps.length; c++) gaps[c] = Math.max(gaps[c], requiredGap);
        }
        return gaps;
    }

    function maxContainerPadding(containers) {
        var maximum = 0, i;
        for (i = 0; i < containers.length; i++) maximum = Math.max(maximum, containerPadding(containers[i]));
        return maximum;
    }

    function containerPadding(container) {
        return Math.max(containerPaddingX(container), containerPaddingY(container));
    }

    function containerPaddingX(container) {
        if (container.sizeClass === "wideNested") return CFG.WIDE_NESTED_PAD_X;
        if (container.padding === "minimal") return CFG.CONTAINER_PAD_MINIMAL;
        return container.padding === "normal" ? CFG.CONTAINER_PAD_NORMAL : CFG.CONTAINER_PAD_TIGHT;
    }

    function containerPaddingY(container) {
        if (container.sizeClass === "wideNested") return Math.max(containerPaddingTop(container), containerPaddingBottom(container, CFG.HORIZONTAL_BOX_HEIGHT));
        if (container.padding === "minimal") return CFG.CONTAINER_PAD_MINIMAL;
        return container.padding === "normal" ? CFG.CONTAINER_PAD_NORMAL : CFG.CONTAINER_PAD_TIGHT;
    }

    function containerPaddingTop(container) {
        if (container.sizeClass === "wideNested") return CFG.WIDE_NESTED_PAD_TOP;
        if (container.labelPosition === "bottomRight") return CFG.BOTTOM_LABEL_PAD_TOP;
        return Math.max(containerPaddingY(container), container.titleHeight ? container.titleHeight + 2 * container.titleGap : 0);
    }

    function containerPaddingBottom(container, memberHeight) {
        if (container.sizeClass === "wideNested") return CFG.WIDE_NESTED_HEIGHT - memberHeight - CFG.WIDE_NESTED_PAD_TOP;
        return Math.max(containerPaddingY(container), container.labelPosition === "bottomRight" && container.titleHeight ? container.titleHeight + 2 * container.titleGap : 0);
    }

    function shaftRouteGap(edge) {
        if (!edge || (edge.shaftLength !== "2mm" && edge.shaftLength !== "3mm")) return CFG.GAP;
        var mode = edge.arrow || "end", inset = 0;
        if (mode === "start" || mode === "both") inset += CFG.ARROW_H / 2;
        if (mode === "end" || mode === "both") inset += CFG.ARROW_H / 2;
        return (edge.shaftLength === "2mm" ? CFG.BUS_LEG : CFG.GAP) + inset;
    }

    function applyContainerSizeClasses(containers, byId) {
        var i, member;
        for (i = 0; i < containers.length; i++) {
            if (containers[i].sizeClass !== "wideNested") continue;
            member = byId[containers[i].members[0]];
            member.w = Math.max(member.w, CFG.WIDE_NESTED_WIDTH - CFG.WIDE_NESTED_PAD_X * 2);
        }
    }

    function containerAwareRowGaps(nodes, containers, edges, gaps) {
        var byId = {}, ranges = {}, containerRanges = [], memberOwners = {}, starts = {}, ends = {}, connectorGaps = {}, i, j, spec, member, firstRow, lastRow, padTop, padBottom, r, edge, fromRange, toRange, boundary;
        for (i = 0; i < nodes.length; i++) {
            byId[nodes[i].id] = nodes[i];
            ranges[nodes[i].id] = { first: nodes[i].row, last: nodes[i].row + nodes[i].rowSpan - 1 };
        }
        for (i = 0; i < containers.length; i++) {
            spec = containers[i]; firstRow = null; lastRow = null;
            for (j = 0; j < spec.members.length; j++) {
                member = byId[spec.members[j]];
                firstRow = firstRow === null ? member.row : Math.min(firstRow, member.row);
                lastRow = lastRow === null ? member.row + member.rowSpan - 1 : Math.max(lastRow, member.row + member.rowSpan - 1);
                if (!memberOwners[member.id]) memberOwners[member.id] = [];
                memberOwners[member.id].push(i);
            }
            containerRanges[i] = { first: firstRow, last: lastRow };
            ranges[spec.id] = containerRanges[i];
        }
        for (i = 0; i < containers.length; i++) {
            spec = containers[i]; firstRow = containerRanges[i].first; lastRow = containerRanges[i].last;
            padTop = containerPaddingTop(spec); padBottom = containerPaddingBottom(spec, 0);
            if (spec.sizeClass === "wideNested") padBottom = containerPaddingBottom(spec, byId[spec.members[0]].h);
            if (firstRow > 0 && !hasSharedBoundary(spec, i, firstRow, true, byId, containerRanges, memberOwners)) starts[firstRow - 1] = Math.max(starts[firstRow - 1] || 0, padTop);
            if (lastRow < gaps.length && !hasSharedBoundary(spec, i, lastRow, false, byId, containerRanges, memberOwners)) ends[lastRow] = Math.max(ends[lastRow] || 0, padBottom);
        }
        for (i = 0; i < edges.length; i++) {
            edge = edges[i]; fromRange = ranges[edge.from]; toRange = ranges[edge.to];
            if (!fromRange || !toRange) continue;
            boundary = null;
            if (edge.fromPort === "bottom" && edge.toPort === "top" && fromRange.last + 1 === toRange.first) boundary = fromRange.last;
            else if (edge.fromPort === "top" && edge.toPort === "bottom" && toRange.last + 1 === fromRange.first) boundary = toRange.last;
            if (boundary !== null) connectorGaps[boundary] = Math.max(connectorGaps[boundary] || 0, shaftRouteGap(edge));
        }
        for (r = 0; r < gaps.length; r++) gaps[r] = Math.max(gaps[r], (ends[r] || 0) + (starts[r] || 0) + (connectorGaps[r] || CFG.GAP));
        return gaps;
    }

    function hasSharedBoundary(spec, ownerIndex, boundaryRow, atStart, byId, containerRanges, memberOwners) {
        var i, j, member, owners, otherRange, memberBoundary;
        for (i = 0; i < spec.members.length; i++) {
            member = byId[spec.members[i]];
            memberBoundary = atStart ? member.row : member.row + member.rowSpan - 1;
            if (memberBoundary !== boundaryRow) continue;
            owners = memberOwners[member.id] || [];
            for (j = 0; j < owners.length; j++) {
                if (owners[j] === ownerIndex) continue;
                otherRange = containerRanges[owners[j]];
                if ((atStart && otherRange.last === boundaryRow) || (!atStart && otherRange.first === boundaryRow)) return true;
            }
        }
        return false;
    }

    function calibratedBoxSize(node, measure, fontSize) {
        var scale = fontSize / 8;
        var lineStep = fontSize === 6 ? CFG.LEADING_6 : fontSize * 1.2;
        if (node.shape === "inputOutput" || node.shape === "predefinedProcess") {
            var measuredHeight = measure.h + CFG.PAD_Y * 2 * scale;
            var safeWidth = measure.w + CFG.HORIZONTAL_PADDING_TOTAL * scale;
            return { w: safeWidth + (node.shape === "inputOutput" ? 8 : 8 * scale), h: measuredHeight };
        }
        if (node.shape === "label") {
            var labelLines = String(node.text).replace(/\r\n|\r/g, "\n").split("\n");
            var labelUnits = 0, labelIndex;
            for (labelIndex = 0; labelIndex < labelLines.length; labelIndex++) labelUnits = Math.max(labelUnits, textUnits(labelLines[labelIndex]));
            return {
                w: (labelUnits * CFG.HORIZONTAL_CHAR_WIDTH + CFG.HORIZONTAL_PADDING_TOTAL) * scale,
                h: measure.h
            };
        }
        if (node.shape === "summer" || node.shape === "multiplier" || node.shape === "plusCircle" || node.shape === "minusCircle") return { w: CFG.OPERATOR_SIZE, h: CFG.OPERATOR_SIZE };
        if (node.shape === "port") return { w: 0, h: 0 };
        if (node.shape === "arrow") {
            if (node.arrowHeads === "both") {
                if (node.arrowDirection === "up" || node.arrowDirection === "down") return { w: Math.max(8.7 * fontSize / 8, measure.w + 6 * fontSize / 8), h: 24 * fontSize / 8 };
                return { w: Math.max(24 * fontSize / 8, measure.w + 6 * fontSize / 8), h: 8.7 * fontSize / 8 };
            }
            if (node.arrowDirection === "up" || node.arrowDirection === "down") return { w: CFG.ARROW_SYMBOL_HEIGHT * fontSize / 8, h: CFG.ARROW_SYMBOL_WIDTH * fontSize / 8 };
            return { w: Math.max(CFG.ARROW_SYMBOL_WIDTH * fontSize / 8, measure.w + 6 * fontSize / 8), h: CFG.ARROW_SYMBOL_HEIGHT * fontSize / 8 };
        }
        if (node.shape === "brace") {
            if (node.braceSide === "top" || node.braceSide === "bottom") return { w: CFG.BRACE_SYMBOL_HEIGHT * fontSize / 8, h: CFG.BRACE_SYMBOL_WIDTH * fontSize / 8 };
            return { w: CFG.BRACE_SYMBOL_WIDTH * fontSize / 8, h: CFG.BRACE_SYMBOL_HEIGHT * fontSize / 8 };
        }
        if (node.shape === "cylinder") return {
            w: CFG.CYLINDER_WIDTH * scale,
            h: CFG.CYLINDER_HEIGHT * scale
        };
        if (node.textDirection === "vertical") {
            var count = String(node.text).replace(/\r\n|\r|\n/g, "").length;
            return {
                w: CFG.VERTICAL_BOX_WIDTH * scale,
                h: count * lineStep + CFG.VERTICAL_PADDING_TOTAL * scale
            };
        }

        var lines = String(node.text).replace(/\r\n|\r/g, "\n").split("\n");
        var units = 0, i;
        for (i = 0; i < lines.length; i++) units = Math.max(units, textUnits(lines[i]));
        var w = (units * CFG.HORIZONTAL_CHAR_WIDTH + CFG.HORIZONTAL_PADDING_TOTAL) * scale;
        var h = Math.max(
            CFG.HORIZONTAL_BOX_HEIGHT * scale + (lines.length - 1) * lineStep,
            measure.h + CFG.PAD_Y * 2 * scale
        );
        if (node.shape === "functionBlock") {
            h = Math.max(h, CFG.HORIZONTAL_BOX_HEIGHT * scale);
        } else if (node.shape === "decision" && lines.length >= 4) {
            w = Math.max(CFG.DECISION_HALF_WIDTH * 2 * scale, w + CFG.DECISION_MULTILINE_PADDING_X * scale);
            h = Math.max(CFG.DECISION_HALF_HEIGHT * 2 * scale, h + CFG.DECISION_MULTILINE_PADDING_Y * scale);
        } else if (node.shape === "decision") {
            var referenceW = (CFG.HORIZONTAL_CHAR_WIDTH * 4 + CFG.HORIZONTAL_PADDING_TOTAL) * scale;
            var referenceH = CFG.HORIZONTAL_BOX_HEIGHT * scale;
            var decisionScale = Math.max(w / referenceW, h / referenceH);
            w = CFG.DECISION_HALF_WIDTH * 2 * scale * decisionScale;
            h = CFG.DECISION_HALF_HEIGHT * 2 * scale * decisionScale;
        } else if (node.shape === "ellipse") {
            w *= CFG.ELLIPSE_SCALE_X;
            h *= CFG.ELLIPSE_SCALE_Y;
        }
        return { w: w, h: h };
    }

    function textUnits(text) {
        var units = 0, i;
        for (i = 0; i < text.length; i++) units += text.charCodeAt(i) <= 255 ? 0.5 : 1;
        return units;
    }

    function branchAwareRowGaps(nodes, edges, maxRow) {
        var gaps = [], byId = {}, outgoing = {}, incoming = {}, r, i, edge, source, target, branches, partition, adjacent;
        for (r = 0; r < maxRow; r++) gaps[r] = CFG.GAP;
        for (i = 0; i < nodes.length; i++) byId[nodes[i].id] = nodes[i];
        for (i = 0; i < edges.length; i++) {
            edge = edges[i];
            if (!outgoing[edge.from]) outgoing[edge.from] = [];
            outgoing[edge.from].push(edge);
            if (!incoming[edge.to]) incoming[edge.to] = [];
            incoming[edge.to].push(edge);
        }
        for (var id in outgoing) {
            if (!outgoing.hasOwnProperty(id) || outgoing[id].length < 2) continue;
            source = byId[id]; branches = outgoing[id];
            if (!source) continue;
            partition = partitionNativeFanoutEdges(branches, source, byId);
            if (partition.bus.length >= 2 && source.row < maxRow) gaps[source.row] = CFG.BUS_LEG * CFG.BRANCH_SEGMENTS;
        }
        for (var targetId in incoming) {
            if (!incoming.hasOwnProperty(targetId)) continue;
            target = byId[targetId]; branches = incoming[targetId]; adjacent = 0;
            if (!target) continue;
            for (i = 0; i < branches.length; i++) {
                source = byId[branches[i].from];
                if (source && branches[i].fromEdge === undefined && branches[i].toEdge === undefined && branches[i].fromPort === undefined && source.row + 1 === target.row) adjacent++;
            }
            if (adjacent >= 2 && target.row > 0) gaps[target.row - 1] = CFG.BUS_LEG * CFG.BRANCH_SEGMENTS;
        }
        return gaps;
    }

    function partitionNativeFanoutEdges(edges, source, byId) {
        var bus = [], residual = [], i, edge, target;
        for (i = 0; i < edges.length; i++) {
            edge = edges[i]; target = byId[edge.to];
            if (source && target && edge.fromEdge === undefined && edge.toEdge === undefined && edge.fromPort === undefined && target.row === source.row + 1) bus.push(edge);
            else residual.push(edge);
        }
        if (bus.length < 2) return { bus: [], residual: edges.slice(0) };
        return { bus: bus, residual: residual };
    }

    function positionLayout(layout, artboard) {
        var abW = artboard[2] - artboard[0], abH = artboard[1] - artboard[3];
        var left = artboard[0] + (abW - layout.width) / 2 + layout.containerMargin + (layout.sideLabelWidth || 0);
        var top = artboard[1] - (abH - layout.height) / 2 - layout.containerMargin;
        var i, n, spanW, spanH;
        layout.left = left; layout.top = top;
        for (i = 0; i < layout.nodes.length; i++) {
            n = layout.nodes[i];
            if (n.columnSpan > 1) {
                spanW = trackSpanSize(layout.colW, n.column, n.columnSpan, layout.columnGaps);
                n.w = Math.max(n.w, spanW);
                n.cx = left + layout.colStarts[n.column] + spanW / 2;
            } else n.cx = left + columnCenter(layout.colCenters, n.column);
            if (n.rowSpan > 1) {
                spanH = trackSpanSize(layout.rowH, n.row, n.rowSpan, layout.rowGaps);
                n.h = Math.max(n.h, spanH);
                n.cy = top - layout.rowStarts[n.row] - spanH / 2;
            } else n.cy = top - layout.rowCenters[n.row];
            n.left = n.cx - n.w / 2; n.right = n.cx + n.w / 2;
            n.top = n.cy + n.h / 2; n.bottom = n.cy - n.h / 2;
        }
        applyVerticalStacks(layout.stackSpecs, layout.byId);
        applyNativeBusCompaction(layout);
        applyHorizontalStacks(layout.horizontalStackSpecs, layout.byId, layout.edges, layout);
        if (layout.swimlaneLayout === "vertical") layout.containers = measureVerticalSwimlanes(layout.containerSpecs, layout.byId);
        else if (layout.swimlaneLayout === "horizontal") layout.containers = measureHorizontalSwimlanes(layout.containerSpecs, layout.byId);
        else {
            layout.containers = measureContainers(layout.containerSpecs, layout.byId, layout.edges);
            equalizeContainerFrameGroups(layout.containers);
            distributeContainerMembers(layout.containerSpecs, layout.containers, layout.byId);
            layout.containers = measureContainers(layout.containerSpecs, layout.byId, layout.edges);
            equalizeContainerFrameGroups(layout.containers);
        }
        if (layout.swimlaneLayout || layout.stackSpecs.length || layout.horizontalStackSpecs.length || layout.sideLabelWidth || hasContainerLayoutConstraints(layout.containerSpecs)) fitPositionedLayout(layout, artboard);
        else setOverlayBounds(layout, layout.left, layout.top, layout.width, layout.height);
        layout.edgeById = buildEndpointMap(layout.byId, layout.containers);
    }

    function applyVerticalStacks(specs, byId) {
        var i, j, previous, current, gap;
        for (i = 0; i < specs.length; i++) {
            gap = specs[i].gap === "minimal" ? CFG.GAP_MINIMAL : CFG.GAP;
            previous = byId[specs[i].members[0]];
            for (j = 1; j < specs[i].members.length; j++) {
                current = byId[specs[i].members[j]];
                current.cy = previous.bottom - gap - current.h / 2;
                current.top = current.cy + current.h / 2; current.bottom = current.cy - current.h / 2;
                current.left = current.cx - current.w / 2; current.right = current.cx + current.w / 2;
                previous = current;
            }
        }
    }

    function compactSiblingBusMembers(members, anchorX) {
        var gap = CFG.GAP_MINIMAL, i, x = 0, firstCenter, lastCenter, shift;
        members.sort(function (a, b) { return a.column - b.column; });
        for (i = 0; i < members.length; i++) {
            members[i].left = x; members[i].right = x + members[i].w; members[i].cx = x + members[i].w / 2;
            x = members[i].right + gap;
        }
        firstCenter = members[0].cx; lastCenter = members[members.length - 1].cx;
        shift = anchorX - (firstCenter + lastCenter) / 2;
        for (i = 0; i < members.length; i++) {
            members[i].cx += shift; members[i].left += shift; members[i].right += shift;
        }
    }

    function nativeMergeGroups(edges, byId) {
        var grouped = {}, result = [], i, edge, target, sources, key;
        for (i = 0; i < edges.length; i++) {
            edge = edges[i];
            if (edge.fromEdge !== undefined || edge.toEdge !== undefined || edge.fromPort !== undefined || !byId[edge.from] || !byId[edge.to]) continue;
            key = edge.to;
            if (!grouped[key]) grouped[key] = [];
            grouped[key].push(edge);
        }
        for (key in grouped) {
            if (!grouped.hasOwnProperty(key) || grouped[key].length < 2) continue;
            target = byId[key]; sources = [];
            for (i = 0; i < grouped[key].length; i++) sources.push(byId[grouped[key][i].from]);
            if (!usesNativeMergeBus(sources, target)) continue;
            result.push({ target: target, sources: sources, edges: grouped[key] });
        }
        return result;
    }

    function usesNativeMergeBus(sources, target) {
        var row, i;
        if (!target || sources.length < 2) return false;
        row = sources[0].row;
        for (i = 0; i < sources.length; i++) if (!sources[i] || sources[i].row !== row || target.row !== row + 1) return false;
        return true;
    }

    function applyNativeBusCompaction(layout) {
        var outgoing = {}, handledRows = {}, merges, i, j, edge, source, targets, key, members, partition;
        for (i = 0; i < layout.edges.length; i++) {
            edge = layout.edges[i];
            if (!outgoing[edge.from]) outgoing[edge.from] = [];
            outgoing[edge.from].push(edge);
        }
        for (key in outgoing) {
            if (!outgoing.hasOwnProperty(key)) continue;
            source = layout.byId[key];
            partition = partitionNativeFanoutEdges(outgoing[key], source, layout.byId);
            if (partition.bus.length < 2) continue;
            targets = [];
            for (i = 0; i < partition.bus.length; i++) targets.push(layout.byId[partition.bus[i].to]);
            compactSiblingBusMembers(targets, source.cx); handledRows[targets[0].row] = true;
        }
        merges = nativeMergeGroups(layout.edges, layout.byId);
        for (i = 0; i < merges.length; i++) {
            members = merges[i].sources;
            if (!handledRows[members[0].row]) compactSiblingBusMembers(members, merges[i].target.cx);
        }
    }

    function applyHorizontalStacks(specs, byId, edges, layout) {
        var i, j, k, spec, members, total, center, x, previous, current, edge, startColumn, endColumn, span, anchorY;
        var verticalMembers = {}, stackSpec;
        for (i = 0; i < layout.stackSpecs.length; i++) {
            stackSpec = layout.stackSpecs[i];
            for (j = 0; j < stackSpec.members.length; j++) verticalMembers[stackSpec.members[j]] = true;
        }
        for (i = 0; i < specs.length; i++) {
            spec = specs[i]; members = []; total = 0;
            for (j = 0; j < spec.members.length; j++) {
                members.push(byId[spec.members[j]]); total += byId[spec.members[j]].w;
                if (j === 0) continue;
                edge = null;
                for (k = 0; k < edges.length; k++) {
                    if ((edges[k].from === spec.members[j - 1] && edges[k].to === spec.members[j]) || (edges[k].from === spec.members[j] && edges[k].to === spec.members[j - 1])) { edge = edges[k]; break; }
                }
                total += shaftRouteGap(edge);
            }
            anchorY = members[0].cy;
            for (j = 0; j < members.length; j++) {
                if (verticalMembers[members[j].id]) { anchorY = members[j].cy; break; }
            }
            startColumn = Math.floor(members[0].column); endColumn = Math.ceil(members[members.length - 1].column);
            span = trackSpanSize(layout.colW, startColumn, endColumn - startColumn + 1, layout.columnGaps);
            center = layout.left + layout.colStarts[startColumn] + span / 2; x = center - total / 2;
            for (j = 0; j < members.length; j++) {
                current = members[j];
                if (j > 0) {
                    edge = null; previous = members[j - 1];
                    for (k = 0; k < edges.length; k++) {
                        if ((edges[k].from === previous.id && edges[k].to === current.id) || (edges[k].from === current.id && edges[k].to === previous.id)) { edge = edges[k]; break; }
                    }
                    x += shaftRouteGap(edge);
                }
                current.cy = anchorY;
                current.cx = x + current.w / 2; current.left = x; current.right = x + current.w;
                current.top = current.cy + current.h / 2; current.bottom = current.cy - current.h / 2;
                x = current.right;
            }
        }
    }

    function fitPositionedLayout(layout, artboard) {
        var left = layout.nodes[0].left, right = layout.nodes[0].right;
        var top = layout.nodes[0].top, bottom = layout.nodes[0].bottom;
        var i, item, artboardCx, artboardCy, dx, dy, overlayLeft;
        for (i = 1; i < layout.nodes.length; i++) {
            item = layout.nodes[i]; left = Math.min(left, item.left); right = Math.max(right, item.right);
            top = Math.max(top, item.top); bottom = Math.min(bottom, item.bottom);
        }
        for (i = 0; i < layout.containers.length; i++) {
            item = layout.containers[i]; left = Math.min(left, item.left); right = Math.max(right, item.right);
            top = Math.max(top, item.top); bottom = Math.min(bottom, item.bottom);
        }
        overlayLeft = left - layout.sideLabelWidth;
        artboardCx = (artboard[0] + artboard[2]) / 2; artboardCy = (artboard[1] + artboard[3]) / 2;
        dx = artboardCx - (overlayLeft + right) / 2; dy = artboardCy - (top + bottom) / 2;
        for (i = 0; i < layout.nodes.length; i++) translateBounds(layout.nodes[i], dx, dy);
        for (i = 0; i < layout.containers.length; i++) translateBounds(layout.containers[i], dx, dy);
        layout.left += dx; layout.top += dy;
        setOverlayBounds(layout, overlayLeft + dx, top + dy, right - overlayLeft, top - bottom);
    }

    function setOverlayBounds(layout, left, top, width, height) {
        layout.overlayLeft = left; layout.overlayTop = top;
        layout.overlayWidth = width; layout.overlayHeight = height;
        layout.width = width; layout.height = height;
    }

    function translateBounds(item, dx, dy) {
        if (item.cx !== undefined) { item.cx += dx; item.cy += dy; }
        if (item.titleX !== undefined) item.titleX += dx;
        if (item.headerBottom !== undefined) item.headerBottom += dy;
        if (item.labelDivider !== undefined) item.labelDivider += dx;
        item.left += dx; item.right += dx; item.top += dy; item.bottom += dy;
    }

    function columnCenter(centers, value) {
        var lo = Math.floor(value), hi = Math.ceil(value);
        if (lo === hi) return centers[lo];
        return (centers[lo] + centers[hi]) / 2;
    }

    function measureContainers(specs, byId, edges) {
        var result = [], i, j, members, frame, spec, padX, padY, cx;
        for (i = 0; i < specs.length; i++) {
            spec = specs[i]; members = [];
            for (j = 0; j < spec.members.length; j++) members.push(byId[spec.members[j]]);
            padX = containerPaddingX(spec); padY = containerPaddingY(spec); frame = containerBounds(members, padX, padY);
            if (spec.sizeClass === "wideNested") {
                cx = (frame.left + frame.right) / 2;
                frame.left = cx - CFG.WIDE_NESTED_WIDTH / 2; frame.right = cx + CFG.WIDE_NESTED_WIDTH / 2;
                frame.top = members[0].top + CFG.WIDE_NESTED_PAD_TOP;
                frame.bottom = frame.top - CFG.WIDE_NESTED_HEIGHT;
            } else {
                frame.top = frame.top - padY + containerPaddingTop(spec);
                frame.bottom = frame.bottom + padY - containerPaddingBottom(spec, 0);
                if (spec.titleWidth && frame.right - frame.left < spec.titleWidth + 2 * padX) { cx = (frame.left + frame.right) / 2; frame.left = cx - spec.titleWidth / 2 - padX; frame.right = cx + spec.titleWidth / 2 + padX; }
            }
            frame.titleHeight = spec.titleHeight; frame.titleGap = spec.titleGap;
            if (spec.titleWidth && spec.labelPosition !== "bottomRight") {
                var entry = null, entryCount = 0, membership = {}, candidate, sourceNode, targetNode;
                for (j = 0; j < spec.members.length; j++) membership[spec.members[j]] = true;
                for (j = 0; j < (edges || []).length; j++) {
                    candidate = edges[j]; sourceNode = byId[candidate.from]; targetNode = byId[candidate.to];
                    if (sourceNode && targetNode && !membership[candidate.from] && membership[candidate.to] && sourceNode.row < targetNode.row && sourceNode.column === targetNode.column && !candidate.via && (!candidate.fromPort || candidate.fromPort === "bottom") && (!candidate.toPort || candidate.toPort === "top")) { entry = candidate; entryCount++; }
                }
                if (entryCount === 1) {
                    var entryPoints = opposingVerticalPortPoints(byId[entry.from], byId[entry.to], "bottom", "top", entry.fromPortPosition, entry.toPortPosition);
                    frame.titleX = entryPoints[1][0] + CFG.STROKE / 2 + 3 + spec.titleWidth / 2;
                    frame.right = Math.max(frame.right, frame.titleX + spec.titleWidth / 2 + padX);
                }
            }
            if(spec.shape === "inputOutput"){frame.left-=4;frame.right+=4;}
            frame.shape=spec.shape;frame.id = spec.id; frame.lineStyle = spec.lineStyle || "solid";
            frame.cornerStyle = spec.cornerStyle || "square";
            frame.label = spec.label; frame.labelPosition = spec.labelPosition || "topCenter";
            frame.frameGroup = spec.frameGroup;
            frame.w = frame.right - frame.left; frame.h = frame.top - frame.bottom;
            frame.cx = (frame.left + frame.right) / 2; frame.cy = (frame.top + frame.bottom) / 2;
            result.push(frame);
        }
        return result;
    }

    function measureVerticalSwimlanes(specs, byId) {
        var content = [], result = [], i, j, spec, members, bounds, padX, padY;
        var top = null, bottom = null, boundaries = [], left, right, frame;
        for (i = 0; i < specs.length; i++) {
            spec = specs[i]; members = [];
            for (j = 0; j < spec.members.length; j++) members.push(byId[spec.members[j]]);
            bounds = containerBounds(members, 0, 0);
            padX = containerPaddingX(spec); padY = containerPaddingY(spec);
            content.push({ bounds: bounds, padX: padX, padY: padY });
            top = top === null ? bounds.top + padY : Math.max(top, bounds.top + padY);
            bottom = bottom === null ? bounds.bottom - padY : Math.min(bottom, bounds.bottom - padY);
        }
        top += CFG.SWIMLANE_HEADER_HEIGHT;
        for (i = 0; i < content.length - 1; i++) {
            boundaries[i] = (content[i].bounds.right + content[i + 1].bounds.left) / 2;
            if (boundaries[i] <= content[i].bounds.right || boundaries[i] >= content[i + 1].bounds.left) {
                boundaries[i] = ((content[i].bounds.left + content[i].bounds.right) / 2 + (content[i + 1].bounds.left + content[i + 1].bounds.right) / 2) / 2;
            }
        }
        for (i = 0; i < specs.length; i++) {
            spec = specs[i];
            left = i === 0 ? content[i].bounds.left - content[i].padX : boundaries[i - 1];
            right = i === specs.length - 1 ? content[i].bounds.right + content[i].padX : boundaries[i];
            frame = { id: spec.id, left: left, right: right, top: top, bottom: bottom };
            frame.headerBottom = top - CFG.SWIMLANE_HEADER_HEIGHT;
            frame.lineStyle = spec.lineStyle || "solid"; frame.cornerStyle = "square";
            frame.label = spec.label; frame.labelPosition = "topCenter"; frame.swimlane = true;
            refreshBounds(frame); result.push(frame);
        }
        return result;
    }

    function measureHorizontalSwimlanes(specs, byId) {
        var content = [], result = [], i, j, spec, members, bounds, padX, padY;
        var left = null, right = null, top = null, bottom = null, boundaries = [], frame;
        for (i = 0; i < specs.length; i++) {
            spec = specs[i]; members = [];
            for (j = 0; j < spec.members.length; j++) members.push(byId[spec.members[j]]);
            bounds = containerBounds(members, 0, 0);
            padX = containerPaddingX(spec); padY = containerPaddingY(spec);
            content.push({ bounds: bounds, padX: padX, padY: padY });
            left = left === null ? bounds.left - padX : Math.min(left, bounds.left - padX);
            right = right === null ? bounds.right + padX : Math.max(right, bounds.right + padX);
            top = top === null ? bounds.top + padY : Math.max(top, bounds.top + padY);
            bottom = bottom === null ? bounds.bottom - padY : Math.min(bottom, bounds.bottom - padY);
        }
        left -= CFG.LAYER_LABEL_BAND;
        for (i = 0; i < content.length - 1; i++) {
            boundaries[i] = (content[i].bounds.bottom + content[i + 1].bounds.top) / 2;
            if (boundaries[i] >= content[i].bounds.bottom || boundaries[i] <= content[i + 1].bounds.top) {
                boundaries[i] = ((content[i].bounds.top + content[i].bounds.bottom) / 2 + (content[i + 1].bounds.top + content[i + 1].bounds.bottom) / 2) / 2;
            }
        }
        for (i = 0; i < specs.length; i++) {
            spec = specs[i];
            frame = {
                id: spec.id,
                left: left,
                right: right,
                top: i === 0 ? top : boundaries[i - 1],
                bottom: i === specs.length - 1 ? bottom : boundaries[i]
            };
            frame.labelDivider = left + CFG.LAYER_LABEL_BAND;
            frame.lineStyle = spec.lineStyle || "solid"; frame.cornerStyle = "square";
            frame.label = spec.label; frame.labelDirection = spec.labelDirection || "horizontal"; frame.labelPosition = "middle"; frame.swimlane = true; frame.swimlaneOrientation = "horizontal";
            refreshBounds(frame); result.push(frame);
        }
        return result;
    }

    function equalizeContainerFrameGroups(containers) {
        var groups = {}, i, frame, group;
        for (i = 0; i < containers.length; i++) {
            frame = containers[i];
            if (!frame.frameGroup) continue;
            group = groups[frame.frameGroup];
            if (!group) groups[frame.frameGroup] = { left: frame.left, right: frame.right };
            else {
                group.left = Math.min(group.left, frame.left);
                group.right = Math.max(group.right, frame.right);
            }
        }
        for (i = 0; i < containers.length; i++) {
            frame = containers[i];
            if (!frame.frameGroup) continue;
            group = groups[frame.frameGroup];
            frame.left = group.left; frame.right = group.right;
            refreshBounds(frame);
        }
    }

    function distributeContainerMembers(specs, containers, byId) {
        var frames = {}, i, j, spec, frame, members, total, available, gap, x, member, dx;
        for (i = 0; i < containers.length; i++) frames[containers[i].id] = containers[i];
        for (i = 0; i < specs.length; i++) {
            spec = specs[i];
            if ((spec.memberDistribution !== "spaceBetween" && spec.memberDistribution !== "compact") || spec.members.length < 2) continue;
            frame = frames[spec.id]; members = []; total = 0;
            for (j = 0; j < spec.members.length; j++) {
                member = byId[spec.members[j]]; members.push(member); total += member.w;
            }
            available = frame.w - containerPaddingX(spec) * 2;
            gap = (available - total) / (members.length - 1);
            if (gap < 0) continue;
            x = frame.left + containerPaddingX(spec);
            if(spec.memberDistribution === "compact"){gap=CFG.GAP_MINIMAL;x=frame.cx-(total+gap*(members.length-1))/2;}
            for (j = 0; j < members.length; j++) {
                member = members[j]; dx = x + member.w / 2 - member.cx;
                translateBounds(member, dx, 0); x = member.right + gap;
            }
        }
    }

    function refreshBounds(item) {
        item.w = item.right - item.left; item.h = item.top - item.bottom;
        item.cx = (item.left + item.right) / 2; item.cy = (item.top + item.bottom) / 2;
    }

    function hasContainerLayoutConstraints(specs) {
        var i;
        for (i = 0; i < specs.length; i++) if (specs[i].frameGroup || specs[i].memberDistribution) return true;
        return false;
    }

    function buildEndpointMap(byId, containers) {
        var result = {}, id, i;
        for (id in byId) if (byId.hasOwnProperty(id)) result[id] = byId[id];
        for (i = 0; i < containers.length; i++) result[containers[i].id] = containers[i];
        return result;
    }

    function containerBounds(nodes, paddingX, paddingY) {
        var left = nodes[0].left, right = nodes[0].right, top = nodes[0].top, bottom = nodes[0].bottom, i;
        for (i = 1; i < nodes.length; i++) {
            left = Math.min(left, nodes[i].left); right = Math.max(right, nodes[i].right);
            top = Math.max(top, nodes[i].top); bottom = Math.min(bottom, nodes[i].bottom);
        }
        return { left: left - paddingX, right: right + paddingX, top: top + paddingY, bottom: bottom - paddingY };
    }

    function drawNodes(nodes, targetLayer, stroke, fill, all, fontSize, font) {
        var i, n, box, tf, shapeW, shapeH, shapeLeft, shapeTop;
        for (i = 0; i < nodes.length; i++) {
            n = nodes[i];
            if (n.shape === "port") continue;
            if (n.shape === "summer" || n.shape === "multiplier" || n.shape === "plusCircle" || n.shape === "minusCircle") {
                drawSignalOperator(n, targetLayer, stroke, all);
                continue;
            }
            if (n.shape === "arrow") {
                drawArrowSymbol(n, targetLayer, stroke, all);
                if (n.text !== "") {
                    var labelInk=measureContainerTitle(n.text,fontSize,font),labelX=n.cx;
                    if(n.arrowLabelSide==="right")labelX=n.cx+labelInk.w/2+3;
                    if(n.arrowLabelSide==="left")labelX=n.cx-labelInk.w/2-3;
                    tf = createText(n.text, labelX, n.top + labelInk.h / 2 + 3 * fontSize / 8, fontSize, font, stroke);
                    tf.name = "AI_FLOW_ARROW_LABEL_" + n.id;
                    all.push(tf);
                }
                continue;
            }
            if (n.shape === "brace") {
                drawBraceSymbol(n, targetLayer, stroke, all);
                continue;
            }
            shapeW = n.w; shapeH = n.h;
            shapeLeft = n.left; shapeTop = n.top;
            if (n.shape === "inputOutput") {
                box = drawInputOutput(n, targetLayer);
            } else if (n.shape === "predefinedProcess") {
                box = drawPredefinedProcess(n, targetLayer, stroke, fontSize, all);
            } else if (n.shape === "cylinder") {
                drawCylinderSymbol(n, targetLayer, stroke, fill, all);
                box = null;
            } else if (n.shape === "waveBlock") {
                box = drawWaveBlock(n, targetLayer, stroke, fill, all);
            } else if (n.shape === "sideCurveBlock") {
                box = drawSideCurveBlock(n, targetLayer, stroke, fill, all);
            } else if (n.shape === "label") box = null;
            else if (n.shape === "process" || n.shape === "functionBlock") box = targetLayer.pathItems.rectangle(shapeTop, shapeLeft, shapeW, shapeH);
            else if (n.shape === "terminator") box = targetLayer.pathItems.roundedRectangle(shapeTop, shapeLeft, shapeW, shapeH, shapeH / 2, shapeH / 2);
            else if (n.shape === "ellipse") box = targetLayer.pathItems.ellipse(shapeTop, shapeLeft, shapeW, shapeH);
            else box = diamond(targetLayer, n, shapeW, shapeH);
            if (box) {
                box.name = "AI_FLOW_NODE_" + n.id;
                box.stroked = true; box.strokeColor = stroke; box.strokeWidth = CFG.STROKE; box.filled = true; box.fillColor = fill;
                try { box.strokeDashes = []; } catch (ignoreNodeDash) {}
                if (n.shape === "decision") try { box.strokeJoin = StrokeJoin.ROUNDENDJOIN; } catch (ignoreJoin) {}
                all.push(box);
            }

            if (n.text !== "") {
                tf = createText(n.text, n.cx, n.cy, fontSize, font, stroke);
                tf.name = "AI_FLOW_TEXT_" + n.id;
                all.push(tf);
            }
        }
    }

    function inputOutputInset(height) { return Math.min(height * 0.25, 4); }

    function drawInputOutput(n, targetLayer) {
        var halfStroke = 0, left = n.left, right = n.right;
        var top = n.top - halfStroke, bottom = n.bottom + halfStroke, inset = inputOutputInset(top - bottom);
        var box = targetLayer.pathItems.add();
        box.setEntirePath([[left + inset, top], [right, top], [right - inset, bottom], [left, bottom]]);
        box.closed = true;
        return box;
    }

    function drawPredefinedProcess(n, targetLayer, stroke, fontSize, all) {
        var halfStroke = 0, left = n.left, right = n.right;
        var top = n.top - halfStroke, bottom = n.bottom + halfStroke, inset = 4 * fontSize / 8;
        var box = targetLayer.pathItems.rectangle(top, left, right - left, top - bottom), line, i;
        for (i = 0; i < 2; i++) {
            line = targetLayer.pathItems.add();
            line.setEntirePath([[i === 0 ? left + inset : right - inset, top], [i === 0 ? left + inset : right - inset, bottom]]);
            line.closed = false; line.filled = false; line.stroked = true;
            line.strokeColor = stroke; line.strokeWidth = CFG.STROKE; line.strokeDashes = [];
            line.name = "AI_FLOW_SUBPROCESS_BAR_" + n.id + "_" + i;
            all.push(line);
        }
        return box;
    }

    function shapeBoundaryPoint(node, port, coordinate) {
        if(node.shape==="ellipse"||node.shape==="decision"){
            var horizontal=port==="left"||port==="right",r=horizontal?node.h/2:node.w/2,delta=Math.max(-r,Math.min(r,coordinate-(horizontal?node.cy:node.cx))),fraction=Math.abs(delta)/r;
            var other=(horizontal?node.w/2:node.h/2)*(node.shape==="ellipse"?Math.sqrt(Math.max(0,1-fraction*fraction)):1-fraction);
            return horizontal?[node.cx+(port==="left"?-other:other),node.cy+delta]:[node.cx+delta,node.cy+(port==="top"?other:-other)];
        }
        var inset = node.shape === "inputOutput" ? inputOutputInset(node.h - CFG.STROKE) : 0;
        if (port === "left" || port === "right") {
            var fraction = Math.max(0, Math.min(1, (coordinate - node.bottom) / node.h));
            return [port === "left" ? node.left + inset * fraction : node.right - inset * (1 - fraction), coordinate];
        }
        var minX = node.left + (port === "top" ? inset : 0);
        var maxX = node.right - (port === "bottom" ? inset : 0);
        return [Math.max(minX, Math.min(maxX, coordinate)), port === "top" ? node.top : node.bottom];
    }

    function drawWaveBlock(n, targetLayer, stroke, fill, all) {
        var left = n.left + CFG.STROKE / 2, right = n.right - CFG.STROKE / 2;
        var top = n.top - CFG.STROKE / 2, bottom = n.bottom + CFG.STROKE / 2;
        var h = top - bottom, sideBottom = bottom + h * 0.22, path;
        path = targetLayer.pathItems.add();
        path.setEntirePath([[left, top], [right, top], [right, sideBottom], [left, bottom + h * 0.06]]);
        path.closed = true; path.stroked = true; path.strokeColor = stroke; path.strokeWidth = CFG.STROKE; path.filled = true; path.fillColor = fill;
        try {
            path.pathPoints[2].rightDirection = [left + (right - left) * 0.5, sideBottom];
            path.pathPoints[3].leftDirection = [left + (right - left) * 0.5, bottom + h * 0.06];
            path.pathPoints[2].pointType = PointType.CORNER;
            path.pathPoints[3].pointType = PointType.CORNER;
        } catch (ignoreWaveCurve) {}
        try { path.strokeDashes = []; } catch (ignoreWaveDash) {}
        return path;
    }

    function drawSideCurveBlock(n, targetLayer, stroke, fill, all) {
        var left = n.left + CFG.STROKE / 2, right = n.right - CFG.STROKE / 2;
        var top = n.top - CFG.STROKE / 2, bottom = n.bottom + CFG.STROKE / 2;
        var h = top - bottom, cy = (top + bottom) / 2, cap = Math.min(h * 0.42, (right - left) * 0.2), path;
        path = targetLayer.pathItems.add();
        path.setEntirePath([[left + cap, top], [right - cap, top], [right, cy], [right - cap, bottom], [left + cap, bottom], [left, cy]]);
        path.closed = true; path.stroked = true; path.strokeColor = stroke; path.strokeWidth = CFG.STROKE; path.filled = true; path.fillColor = fill;
        try {
            path.pathPoints[1].rightDirection = [right - cap * 0.35, top];
            path.pathPoints[2].leftDirection = [right, top - h * 0.3];
            path.pathPoints[2].rightDirection = [right, bottom + h * 0.3];
            path.pathPoints[3].leftDirection = [right - cap * 0.35, bottom];
            path.pathPoints[4].rightDirection = [left + cap * 0.35, bottom];
            path.pathPoints[5].leftDirection = [left, bottom + h * 0.3];
            path.pathPoints[5].rightDirection = [left, top - h * 0.3];
            path.pathPoints[0].leftDirection = [left + cap * 0.35, top];
        } catch (ignoreSideCurve) {}
        try { path.strokeDashes = []; } catch (ignoreSideDash) {}
        return path;
    }

    function drawCylinderSymbol(n, targetLayer, stroke, fill, all) {
        var rim = Math.min(CFG.CYLINDER_RIM_HEIGHT * n.h / CFG.HORIZONTAL_BOX_HEIGHT, n.h * 0.28);
        var left = n.left + CFG.STROKE / 2, right = n.right - CFG.STROKE / 2;
        var top = n.top - CFG.STROKE / 2, bottom = n.bottom + CFG.STROKE / 2;
        var topCenter = top - rim / 2, bottomCenter = bottom + rim / 2, bottomEdge = bottomCenter - rim / 2;
        var body = targetLayer.pathItems.add();
        body.setEntirePath([[left, topCenter], [right, topCenter], [right, bottomCenter], [(left + right) / 2, bottomEdge], [left, bottomCenter]]);
        body.closed = true; body.stroked = true; body.strokeColor = stroke; body.strokeWidth = CFG.STROKE; body.filled = true; body.fillColor = fill;
        try { body.strokeDashes = []; } catch (ignoreCylinderDash) {}
        try {
            body.pathPoints[3].leftDirection = [left + (right - left) * 0.25, bottomCenter];
            body.pathPoints[3].rightDirection = [right - (right - left) * 0.25, bottomCenter];
            body.pathPoints[3].pointType = PointType.SMOOTH;
        } catch (ignoreCurve) {}
        body.name = "AI_FLOW_NODE_" + n.id; all.push(body);

        var topRim = targetLayer.pathItems.ellipse(top, left, right - left, rim);
        topRim.stroked = true; topRim.strokeColor = stroke; topRim.strokeWidth = CFG.STROKE; topRim.filled = true; topRim.fillColor = fill;
        try { topRim.strokeDashes = []; } catch (ignoreCylinderRimDash) {}
        topRim.name = "AI_FLOW_NODE_" + n.id + "_TOP"; all.push(topRim);
    }

    function drawArrowSymbol(n, targetLayer, stroke, all) {
        var left = n.left, right = n.right, top = n.top, bottom = n.bottom, h = top - bottom, w = right - left;
        var direction = n.arrowDirection || "right", both = n.arrowHeads === "both", midX = (left + right) / 2, midY = (top + bottom) / 2, shaftH, shaftEnd, points;
        var p = targetLayer.pathItems.add();
        if (both && (direction === "right" || direction === "left")) {
            shaftH = h * 0.48;
            points = [[left + w * 0.25, top], [left, midY], [left + w * 0.25, bottom], [left + w * 0.25, midY - shaftH / 2], [right - w * 0.25, midY - shaftH / 2], [right - w * 0.25, bottom], [right, midY], [right - w * 0.25, top], [right - w * 0.25, midY + shaftH / 2], [left + w * 0.25, midY + shaftH / 2]];
        } else if (both) {
            shaftH = w * 0.48;
            points = [[left, top - h * 0.25], [midX, top], [right, top - h * 0.25], [midX + shaftH / 2, top - h * 0.25], [midX + shaftH / 2, bottom + h * 0.25], [right, bottom + h * 0.25], [midX, bottom], [left, bottom + h * 0.25], [midX - shaftH / 2, bottom + h * 0.25], [midX - shaftH / 2, top - h * 0.25]];
        } else if (direction === "left") {
            shaftH = h * 0.48; shaftEnd = right - w * 0.48;
            points = [[right, midY + shaftH / 2], [shaftEnd, midY + shaftH / 2], [shaftEnd, top], [left, midY], [shaftEnd, bottom], [shaftEnd, midY - shaftH / 2], [right, midY - shaftH / 2]];
        } else if (direction === "up" || direction === "down") {
            shaftH = w * 0.48; shaftEnd = direction === "up" ? bottom + h * 0.48 : top - h * 0.48;
            if (direction === "up") points = [[midX - shaftH / 2, bottom], [midX - shaftH / 2, shaftEnd], [left, shaftEnd], [midX, top], [right, shaftEnd], [midX + shaftH / 2, shaftEnd], [midX + shaftH / 2, bottom]];
            else points = [[midX - shaftH / 2, top], [midX - shaftH / 2, shaftEnd], [left, shaftEnd], [midX, bottom], [right, shaftEnd], [midX + shaftH / 2, shaftEnd], [midX + shaftH / 2, top]];
        } else {
            shaftH = h * 0.48; shaftEnd = left + w * 0.48;
            points = [[left, midY + shaftH / 2], [shaftEnd, midY + shaftH / 2], [shaftEnd, top], [right, midY], [shaftEnd, bottom], [shaftEnd, midY - shaftH / 2], [left, midY - shaftH / 2]];
        }
        p.setEntirePath(points);
        p.closed = true; p.filled = false; p.stroked = true; p.strokeColor = stroke; p.strokeWidth = CFG.STROKE;
        try { p.strokeDashes = []; } catch (ignoreArrowDash) {}
        p.name = "AI_FLOW_NODE_" + n.id; all.push(p);
    }

    function drawBraceSymbol(n, targetLayer, stroke, all) {
        var left = n.left, right = n.right, top = n.top, bottom = n.bottom, midX = (left + right) / 2, midY = (top + bottom) / 2;
        var side = n.braceSide || "left", w = right - left, h = top - bottom, points;
        var p = targetLayer.pathItems.add();
        if (side === "right") {
            points = [[right - w * 0.64, top], [right - w * 0.36, top - h * 0.08], [right - w * 0.36, midY - h * 0.08], [right, midY], [right - w * 0.36, midY + h * 0.08], [right - w * 0.36, bottom + h * 0.08], [right - w * 0.64, bottom]];
        } else if (side === "top") {
            points = [[left, bottom + h * 0.64], [left + w * 0.08, bottom + h * 0.36], [midX - w * 0.08, bottom + h * 0.36], [midX, top], [midX + w * 0.08, bottom + h * 0.36], [right - w * 0.08, bottom + h * 0.36], [right, bottom + h * 0.64]];
        } else if (side === "bottom") {
            points = [[left, top - h * 0.64], [left + w * 0.08, top - h * 0.36], [midX - w * 0.08, top - h * 0.36], [midX, bottom], [midX + w * 0.08, top - h * 0.36], [right - w * 0.08, top - h * 0.36], [right, top - h * 0.64]];
        } else {
            points = [[left + w * 0.64, top], [left + w * 0.36, top - h * 0.08], [left + w * 0.36, midY - h * 0.08], [left, midY], [left + w * 0.36, midY + h * 0.08], [left + w * 0.36, bottom + h * 0.08], [left + w * 0.64, bottom]];
        }
        p.setEntirePath(points);
        p.closed = false; p.filled = false; p.stroked = true; p.strokeColor = stroke; p.strokeWidth = CFG.STROKE;
        try { p.strokeDashes = []; } catch (ignoreBraceDash) {}
        try {
            p.pathPoints[3].leftDirection = points[3];
            p.pathPoints[3].rightDirection = points[3];
        } catch (ignoreBrace) {}
        p.name = "AI_FLOW_NODE_" + n.id; all.push(p);
    }

    function drawSignalOperator(n, targetLayer, stroke, all) {
        var size = CFG.OPERATOR_SIZE, half = size / 2, arm = half - CFG.OPERATOR_STROKE / 2 - CFG.OPERATOR_GAP;
        var circle = targetLayer.pathItems.ellipse(n.cy + half, n.cx - half, size, size);
        styleSignalPath(circle, stroke); circle.closed = true; circle.name = "AI_FLOW_NODE_" + n.id; all.push(circle);
        if (arm < CFG.OPERATOR_STROKE) arm = CFG.OPERATOR_STROKE;
        if (n.shape === "summer" || n.shape === "plusCircle") {
            addOperatorLine(targetLayer, [[n.cx - arm, n.cy], [n.cx + arm, n.cy]], stroke, all, n.id);
            addOperatorLine(targetLayer, [[n.cx, n.cy + arm], [n.cx, n.cy - arm]], stroke, all, n.id);
        } else if (n.shape === "minusCircle") {
            addOperatorLine(targetLayer, [[n.cx - arm, n.cy], [n.cx + arm, n.cy]], stroke, all, n.id);
        } else {
            addOperatorLine(targetLayer, [[n.cx - arm * 0.7, n.cy + arm * 0.7], [n.cx + arm * 0.7, n.cy - arm * 0.7]], stroke, all, n.id);
            addOperatorLine(targetLayer, [[n.cx - arm * 0.7, n.cy - arm * 0.7], [n.cx + arm * 0.7, n.cy + arm * 0.7]], stroke, all, n.id);
        }
    }

    function addOperatorLine(targetLayer, points, stroke, all, id) {
        var line = targetLayer.pathItems.add();
        line.setEntirePath(points); line.closed = false; styleSignalPath(line, stroke);
        try { line.strokeCap = StrokeCap.BUTTENDCAP; } catch (ignoreCap) {}
        line.name = "AI_FLOW_NODE_" + id + "_MARK"; all.push(line);
    }

    function styleSignalPath(path, stroke) {
        path.filled = false; path.stroked = true; path.strokeColor = stroke; path.strokeWidth = CFG.OPERATOR_STROKE;
        try { path.strokeDashes = []; } catch (ignoreOperatorDash) {}
    }

    function diamond(targetLayer, n, shapeW, shapeH) {
        var p = targetLayer.pathItems.add();
        p.setEntirePath([
            [n.cx, n.cy + shapeH / 2],
            [n.cx + shapeW / 2, n.cy],
            [n.cx, n.cy - shapeH / 2],
            [n.cx - shapeW / 2, n.cy]
        ]);
        p.closed = true; return p;
    }

    function drawContainers(containers, targetLayer, stroke, all, fontSize, font) {
        var i, frame, path, point;
        if (containers.length && containers[0].swimlane) {
            if (containers[0].swimlaneOrientation === "horizontal") drawHorizontalSwimlaneFrame(containers, targetLayer, stroke, all, fontSize, font);
            else drawVerticalSwimlaneFrame(containers, targetLayer, stroke, all, fontSize, font);
            return;
        }
        for (i = 0; i < containers.length; i++) {
            frame = containers[i];
            if(frame.shape === "inputOutput") { path=drawInputOutput(frame,targetLayer); } else if (frame.cornerStyle === "rounded") {
                var radius = Math.min(CFG.CONTAINER_ROUND_RADIUS, (frame.right - frame.left) / 2, (frame.top - frame.bottom) / 2);
                path = targetLayer.pathItems.roundedRectangle(frame.top, frame.left, frame.right - frame.left, frame.top - frame.bottom, radius, radius);
            } else path = targetLayer.pathItems.rectangle(frame.top, frame.left, frame.right - frame.left, frame.top - frame.bottom);
            path.stroked = true; path.strokeColor = stroke; path.strokeWidth = CFG.STROKE; path.filled = false;
            var frameDashes = lineStyleDashes(frame.lineStyle);
            try { path.strokeDashes = frameDashes; } catch (ignoreDash) {}
            path.name = "AI_FLOW_CONTAINER_" + frame.id; all.push(path);
            if (frame.label) {
                point = containerLabelPoint(frame);
                addEdgeLabel(frame.label, point[0], point[1], all, fontSize, font, stroke);
            }
        }
    }

    function verticalSwimlaneFrameGeometry(containers) {
        var dividers = [], i, first = containers[0], last = containers[containers.length - 1];
        for (i = 0; i < containers.length - 1; i++) dividers.push(containers[i].right);
        return {
            left: first.left, right: last.right, top: first.top, bottom: first.bottom,
            headerBottom: first.headerBottom, dividers: dividers
        };
    }

    function drawVerticalSwimlaneFrame(containers, targetLayer, stroke, all, fontSize, font) {
        var geometry = verticalSwimlaneFrameGeometry(containers), path, line, i, point, frame, dashes = lineStyleDashes(containers[0].lineStyle);
        path = targetLayer.pathItems.rectangle(geometry.top, geometry.left, geometry.right - geometry.left, geometry.top - geometry.bottom);
        path.stroked = true; path.strokeColor = stroke; path.strokeWidth = CFG.STROKE; path.filled = false;
        try { path.strokeDashes = dashes; } catch (ignoreFrameDash) {}
        path.name = "AI_FLOW_SWIMLANE_FRAME"; all.push(path);

        line = targetLayer.pathItems.add();
        line.setEntirePath([[geometry.left, geometry.headerBottom], [geometry.right, geometry.headerBottom]]);
        line.stroked = true; line.strokeColor = stroke; line.strokeWidth = CFG.STROKE; line.filled = false;
        try { line.strokeDashes = dashes; } catch (ignoreHeaderDash) {}
        line.name = "AI_FLOW_SWIMLANE_HEADER"; all.push(line);

        for (i = 0; i < geometry.dividers.length; i++) {
            line = targetLayer.pathItems.add();
            line.setEntirePath([[geometry.dividers[i], geometry.top], [geometry.dividers[i], geometry.bottom]]);
            line.stroked = true; line.strokeColor = stroke; line.strokeWidth = CFG.STROKE; line.filled = false;
            try { line.strokeDashes = dashes; } catch (ignoreDividerDash) {}
            line.name = "AI_FLOW_SWIMLANE_DIVIDER_" + (i + 1); all.push(line);
        }
        for (i = 0; i < containers.length; i++) {
            frame = containers[i];
            if (!frame.label) continue;
            point = containerLabelPoint(frame);
            addEdgeLabel(frame.label, point[0], point[1], all, fontSize, font, stroke, frame.labelDirection === "vertical");
        }
    }

    function horizontalSwimlaneFrameGeometry(containers) {
        var dividers = [], i, first = containers[0], last = containers[containers.length - 1];
        for (i = 0; i < containers.length - 1; i++) dividers.push(containers[i].bottom);
        return {
            left: first.left, right: first.right, top: first.top, bottom: last.bottom,
            labelDivider: first.labelDivider, dividers: dividers
        };
    }

    function drawHorizontalSwimlaneFrame(containers, targetLayer, stroke, all, fontSize, font) {
        var geometry = horizontalSwimlaneFrameGeometry(containers), path, line, i, point, frame, dashes = lineStyleDashes(containers[0].lineStyle);
        path = targetLayer.pathItems.rectangle(geometry.top, geometry.left, geometry.right - geometry.left, geometry.top - geometry.bottom);
        path.stroked = true; path.strokeColor = stroke; path.strokeWidth = CFG.STROKE; path.filled = false;
        try { path.strokeDashes = dashes; } catch (ignoreDash) {}
        path.name = "AI_FLOW_SWIMLANE_FRAME"; all.push(path);

        for (i = 0; i < geometry.dividers.length; i++) {
            line = targetLayer.pathItems.add();
            line.setEntirePath([[geometry.left, geometry.dividers[i]], [geometry.right, geometry.dividers[i]]]);
            line.stroked = true; line.strokeColor = stroke; line.strokeWidth = CFG.STROKE; line.filled = false;
            try { line.strokeDashes = dashes; } catch (ignoreDash2) {}
            line.name = "AI_FLOW_SWIMLANE_DIVIDER_" + (i + 1); all.push(line);
        }
        line = targetLayer.pathItems.add();
        line.setEntirePath([[geometry.labelDivider, geometry.top], [geometry.labelDivider, geometry.bottom]]);
        line.stroked = true; line.strokeColor = stroke; line.strokeWidth = CFG.STROKE; line.filled = false;
        try { line.strokeDashes = dashes; } catch (ignoreDash3) {}
        line.name = "AI_FLOW_SWIMLANE_LABEL_DIVIDER"; all.push(line);

        for (i = 0; i < containers.length; i++) {
            frame = containers[i];
            if (!frame.label) continue;
            point = containerLabelPoint(frame);
            addEdgeLabel(frame.label, point[0], point[1], all, fontSize, font, stroke);
        }
    }

    function containerLabelPoint(frame) {
        if (frame.labelPosition === "bottomRight") return [frame.right - 20, frame.bottom + (frame.titleHeight ? frame.titleGap + frame.titleHeight / 2 : 7)];
        if (frame.swimlaneOrientation === "horizontal") return [(frame.left + frame.labelDivider) / 2, (frame.top + frame.bottom) / 2];
        if (frame.swimlane) return [(frame.left + frame.right) / 2, (frame.top + frame.headerBottom) / 2 + 3];
        return [frame.titleX !== undefined ? frame.titleX : (frame.left + frame.right) / 2, frame.top - (frame.titleHeight ? frame.titleGap + frame.titleHeight / 2 : 7)];
    }

    function edgeMidpoint(points) {
        var lengths = [], total = 0, i, dx, dy, length, target, traversed = 0, ratio;
        for (i = 0; i < points.length - 1; i++) {
            dx = points[i + 1][0] - points[i][0]; dy = points[i + 1][1] - points[i][1];
            length = Math.sqrt(dx * dx + dy * dy); lengths.push(length); total += length;
        }
        target = total / 2;
        for (i = 0; i < lengths.length; i++) {
            if (traversed + lengths[i] >= target) {
                ratio = lengths[i] === 0 ? 0 : (target - traversed) / lengths[i];
                return [points[i][0] + (points[i + 1][0] - points[i][0]) * ratio, points[i][1] + (points[i + 1][1] - points[i][1]) * ratio];
            }
            traversed += lengths[i];
        }
        return [points[points.length - 1][0], points[points.length - 1][1]];
    }

    function pointEndpoint(id, point) {
        return { id: id, cx: point[0], cy: point[1], left: point[0], right: point[0], top: point[1], bottom: point[1], w: 0, h: 0 };
    }

    function drawEdges(edges, byId, layout, targetLayer, stroke, all, fontSize, font) {
        var groups = {}, order = [], derived = [], routes = {}, mergeKeys = {}, merges, i, j, e, points, source, target, key;
        merges = nativeMergeGroups(edges, byId);
        for (i = 0; i < merges.length; i++) {
            for (j = 0; j < merges[i].edges.length; j++) mergeKeys[merges[i].edges[j].from + "\u0000" + merges[i].edges[j].to] = true;
        }
        for (i = 0; i < edges.length; i++) {
            e = edges[i];
            if (e.fromEdge !== undefined || e.toEdge !== undefined) { derived.push(e); continue; }
            key = e.from + "\u0000" + e.to;
            if (mergeKeys[key]) continue;
            if (!groups[e.from]) { groups[e.from] = []; order.push(e.from); }
            groups[e.from].push(e);
        }
        for (i = 0; i < order.length; i++) drawEdgeGroup(groups[order[i]], byId, layout, targetLayer, stroke, all, fontSize, font, routes);
        for (i = 0; i < merges.length; i++) drawNativeMergeGroup(merges[i], targetLayer, stroke, all, fontSize, font);
        for (i = 0; i < derived.length; i++) {
            e = derived[i];
            source = e.fromEdge !== undefined ? pointEndpoint(e.fromEdge + "_middle", edgeMidpoint(routes[e.fromEdge])) : byId[e.from];
            target = e.toEdge !== undefined ? pointEndpoint(e.toEdge + "_middle", edgeMidpoint(routes[e.toEdge])) : byId[e.to];
            points = drawSingleEdge(source, target, e, layout, targetLayer, stroke, all, fontSize, font);
            if (e.id !== undefined) routes[e.id] = points;
        }
    }

    function drawEdgeGroup(edges, byId, layout, targetLayer, stroke, all, fontSize, font, routes) {
        var source = byId[edges[0].from], partition = partitionNativeFanoutEdges(edges, source, byId), busTargets = [], i, edge, target, points, geometry, labelPoint;
        if (partition.bus.length >= 2) {
            for (i = 0; i < partition.bus.length; i++) busTargets.push(byId[partition.bus[i].to]);
            geometry = fanoutBusGeometry(source, busTargets, CFG.BUS_LEG);
            addLine(targetLayer, geometry.trunk, stroke, all);
            addLine(targetLayer, geometry.bus, stroke, all);
            for (i = 0; i < partition.bus.length; i++) {
                edge = partition.bus[i]; target = busTargets[i];
                addRoutedLine(targetLayer, geometry.spokes[i], edge.arrow || "end", stroke, all, edge.lineStyle);
                if (edge.id !== undefined) routes[edge.id] = compactPoints([geometry.trunk[0], geometry.trunk[1], [target.cx, geometry.bus[0][1]], geometry.spokes[i][1]]);
                if (edge.label) {
                    if (edge.labelPosition === "source") labelPoint = busSourceLabelPoint(source, edge.labelSide);
                    else if (edge.labelPosition === "target") labelPoint = busTargetLabelPoint(target, edge.labelSide);
                    else labelPoint = busTargetLabelPoint({ cx: target.cx, top: (geometry.spokes[i][0][1] + target.top) / 2 }, edge.labelSide);
                    addEdgeLabel(edge.label, labelPoint[0], labelPoint[1], all, fontSize, font, stroke);
                }
            }
        }
        for (i = 0; i < partition.residual.length; i++) {
            edge = partition.residual[i];
            points = drawSingleEdge(source, byId[edge.to], edge, layout, targetLayer, stroke, all, fontSize, font);
            if (edge.id !== undefined) routes[edge.id] = points;
        }
    }

    function busSourceLabelPoint(source, labelSide) {
        var left = labelSide === "left";
        return [source.cx + (left ? -10 : 10), source.bottom - 2];
    }

    function busTargetLabelPoint(target, labelSide) {
        var left = labelSide === "left";
        return [target.cx + (left ? -10 : 10), target.top + 4];
    }

    function fanoutBusGeometry(source, targets, leg) {
        var busY = source.bottom - leg, minX = targets[0].cx, maxX = targets[0].cx, spokes = [], i;
        for (i = 1; i < targets.length; i++) { minX = Math.min(minX, targets[i].cx); maxX = Math.max(maxX, targets[i].cx); }
        for (i = 0; i < targets.length; i++) spokes.push([[targets[i].cx, busY], [targets[i].cx, targets[i].top]]);
        return { trunk: [[source.cx, source.bottom], [source.cx, busY]], bus: [[minX, busY], [maxX, busY]], spokes: spokes };
    }

    function mergeBusGeometry(sources, target, leg) {
        var busY = sources[0].bottom - leg, minX = sources[0].cx, maxX = sources[0].cx, spokes = [], midX, turnY, outlet, i;
        for (i = 1; i < sources.length; i++) {
            busY = Math.min(busY, sources[i].bottom - leg); minX = Math.min(minX, sources[i].cx); maxX = Math.max(maxX, sources[i].cx);
        }
        for (i = 0; i < sources.length; i++) spokes.push([[sources[i].cx, sources[i].bottom], [sources[i].cx, busY]]);
        midX = (minX + maxX) / 2;
        if (target.cx >= minX && target.cx <= maxX) outlet = [[target.cx, busY], [target.cx, target.top]];
        else {
            turnY = busY - leg;
            outlet = [[midX, busY], [midX, turnY], [target.cx, turnY], [target.cx, target.top]];
        }
        return { spokes: spokes, bus: [[minX, busY], [maxX, busY]], outlet: outlet };
    }

    function drawNativeMergeGroup(group, targetLayer, stroke, all, fontSize, font) {
        var geometry = mergeBusGeometry(group.sources, group.target, CFG.BUS_LEG), i, labelPoint;
        for (i = 0; i < geometry.spokes.length; i++) {
            addLine(targetLayer, geometry.spokes[i], stroke, all, group.edges[i].lineStyle);
            if (group.edges[i].label) {
                labelPoint = offsetLabel(geometry.spokes[i][0], "bottom", false);
                addEdgeLabel(group.edges[i].label, labelPoint[0], labelPoint[1], all, fontSize, font, stroke);
            }
        }
        addLine(targetLayer, geometry.bus, stroke, all);
        addRoutedLine(targetLayer, geometry.outlet, group.edges[0].arrow || "end", stroke, all, group.edges[0].lineStyle);
    }

    function drawSingleEdge(source, target, edge, layout, targetLayer, stroke, all, fontSize, font) {
        var ports = automaticPorts(source, target);
        var fromPort = edge.fromPort || ports.fromPort, toPort = edge.toPort || ports.toPort;
        if(edge.routeStyle === "curve") return drawCurvedEdge(source,target,edge,fromPort,toPort,targetLayer,stroke,all,fontSize,font);
        var points = routedPoints(source, target, fromPort, toPort, edge.via, layout, edge.routeStyle, edge.fromPortPosition, edge.toPortPosition, edge.routeLane);
        addRoutedLine(targetLayer, points, edge.arrow || "end", stroke, all, edge.lineStyle);
        if (edge.label) {
            var labelPoint = edgeLabelPoint(edge, points, source, fromPort, toPort, fontSize, font);
            addEdgeLabel(edge.label, labelPoint[0], labelPoint[1], all, fontSize, font, stroke);
        }
        return points;
    }

    function drawCurvedEdge(source,target,edge,fromPort,toPort,targetLayer,stroke,all,fontSize,font){
        if(fromPort!==toPort||(fromPort!=="top"&&fromPort!=="bottom"))throw "Curve requires matching top/bottom ports";
        var a=portPoint(source,fromPort,edge.fromPortPosition),b=portPoint(target,toPort,edge.toPortPosition),dx=b[0]-a[0],sign=fromPort==="top"?1:-1;
        var rise=Math.max(CFG.GAP,Math.abs(dx)*0.22),c=[a[0]+dx/3,a[1]+sign*rise*4/3],d=[b[0]-dx/3,b[1]+sign*rise*4/3];
        var curve=addLine(targetLayer,[a,b],stroke,all,edge.lineStyle);curve.pathPoints[0].rightDirection=c;curve.pathPoints[1].leftDirection=d;
        if((edge.arrow||"end")!=="none")addArrow(targetLayer,b[0],b[1],b[0]-d[0],b[1]-d[1],stroke,all);
        var mid=[(a[0]+b[0])/2,(a[1]+b[1])/2+sign*rise];
        if(edge.label){var m=measureContainerTitle(edge.label,fontSize,font);addEdgeLabel(edge.label,mid[0],mid[1]+sign*(m.h/2+3),all,fontSize,font,stroke);}
        return [a,mid,b];
    }

    function validateRoutedEdges(edges, byId, layout) {
        var i, edge, source, target, ports, fromPort, toPort, points, routes = {};
        for (i = 0; i < edges.length; i++) {
            edge = edges[i];
            source = edge.fromEdge !== undefined ? pointEndpoint(edge.fromEdge + "_middle", edgeMidpoint(routes[edge.fromEdge])) : byId[edge.from];
            target = edge.toEdge !== undefined ? pointEndpoint(edge.toEdge + "_middle", edgeMidpoint(routes[edge.toEdge])) : byId[edge.to];
            ports = automaticPorts(source, target);
            fromPort = edge.fromPort || ports.fromPort; toPort = edge.toPort || ports.toPort;
            points = routedPoints(source, target, fromPort, toPort, edge.via, layout, edge.routeStyle, edge.fromPortPosition, edge.toPortPosition, edge.routeLane);
            if (edge.id !== undefined) routes[edge.id] = points;
        }
    }

    function automaticPorts(source, target) {
        var dx = target.cx - source.cx, dy = target.cy - source.cy;
        if (Math.abs(dy) >= Math.abs(dx)) {
            return dy < 0 ? { fromPort: "bottom", toPort: "top" } : { fromPort: "top", toPort: "bottom" };
        }
        return dx > 0 ? { fromPort: "right", toPort: "left" } : { fromPort: "left", toPort: "right" };
    }

    function portPoint(node, port, position) {
        var x = node.cx, y = node.cy, anchor = position || "center";
        if (port === "left" || port === "right") {
            if (anchor === "upper") y = node.cy + node.h / 3;
            else if (anchor === "lower") y = node.cy - node.h / 3;
            return shapeBoundaryPoint(node, port, y);
        }
        if (anchor === "left") x = node.cx - node.w / 3;
        else if (anchor === "right") x = node.cx + node.w / 3;
        return shapeBoundaryPoint(node, port, x);
    }

    function axisCenter(centers, value) {
        var last = centers.length - 1, lo, hi, ratio, step;
        if (centers.length === 1) return centers[0];
        if (value <= 0) return centers[0] + value * (centers[1] - centers[0]);
        if (value >= last) return centers[last] + (value - last) * (centers[last] - centers[last - 1]);
        lo = Math.floor(value); hi = Math.ceil(value);
        if (lo === hi) return centers[lo];
        ratio = value - lo; step = centers[hi] - centers[lo];
        return centers[lo] + step * ratio;
    }

    function routeAxis(value, start, end, grid) {
        if (value === "from") return start;
        if (value === "to") return end;
        if (value === "from+gap") return start + CFG.GAP;
        if (value === "from-gap") return start - CFG.GAP;
        if (value === "to+gap") return end + CFG.GAP;
        if (value === "to-gap") return end - CFG.GAP;
        return grid;
    }

    function gridPoint(layout, spec, start, end) {
        var x = routeAxis(spec.x, start[0], end[0], layout.left + axisCenter(layout.colCenters, spec.x));
        var y = routeAxis(spec.y, start[1], end[1], layout.top - axisCenter(layout.rowCenters, spec.y));
        return [x, y];
    }

    function routedPoints(source, target, fromPort, toPort, via, layout, routeStyle, fromPortPosition, toPortPosition, routeLane) {
        if (routeStyle === "straight") return [portPoint(source, fromPort, fromPortPosition), portPoint(target, toPort, toPortPosition)];
        if (!via || via.length === 0) return orthogonalPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition, routeLane);
        var start = portPoint(source, fromPort, fromPortPosition), end = portPoint(target, toPort, toPortPosition), points = [start], i;
        for (i = 0; i < via.length; i++) points.push(gridPoint(layout, via[i], start, end));
        points.push(end); points = compactPoints(points);
        for (i = 0; i < points.length - 1; i++) {
            if (points[i][0] !== points[i + 1][0] && points[i][1] !== points[i + 1][1]) throw "连接 " + source.id + " -> " + target.id + " 的 via 产生了斜线。";
        }
        return points;
    }

    function opposingHorizontalPortPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition) {
        var start = portPoint(source, fromPort, fromPortPosition), end = portPoint(target, toPort, toPortPosition);
        var opposing = (fromPort === "left" && toPort === "right") || (fromPort === "right" && toPort === "left");
        var overlapTop, overlapBottom, y;
        if (!opposing) return [start, end];
        overlapTop = Math.min(source.top, target.top); overlapBottom = Math.max(source.bottom, target.bottom);
        if (overlapTop < overlapBottom) return [start, end];
        y = source.h <= target.h ? source.cy : target.cy;
        y = Math.max(overlapBottom, Math.min(overlapTop, y));
        start = shapeBoundaryPoint(source, fromPort, y); end = shapeBoundaryPoint(target, toPort, y);
        return [start, end];
    }

    function opposingVerticalPortPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition) {
        var start = portPoint(source, fromPort, fromPortPosition), end = portPoint(target, toPort, toPortPosition);
        var opposing = (fromPort === "top" && toPort === "bottom") || (fromPort === "bottom" && toPort === "top");
        var overlapLeft, overlapRight, x;
        if (!opposing) return [start, end];
        overlapLeft = Math.max(shapeBoundaryPoint(source, fromPort, source.left)[0], shapeBoundaryPoint(target, toPort, target.left)[0]);
        overlapRight = Math.min(shapeBoundaryPoint(source, fromPort, source.right)[0], shapeBoundaryPoint(target, toPort, target.right)[0]);
        if (overlapLeft > overlapRight) return [start, end];
        x = source.w <= target.w ? source.cx : target.cx;
        x = Math.max(overlapLeft, Math.min(overlapRight, x));
        start[0] = x; end[0] = x;
        return [start, end];
    }

    function orthogonalPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition, routeLane) {
        var endpoints = (fromPort === "top" || fromPort === "bottom") ?
            opposingVerticalPortPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition) :
            opposingHorizontalPortPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition);
        var start = endpoints[0], end = endpoints[1], points, lane, mid;
        var startOut, endOut, corner, sourceOk, targetOk, laneOffset = CFG.GAP * (routeLane || 1);

        if (fromPort === toPort) {
            if (fromPort === "left") {
                lane = Math.min(source.left, target.left) - laneOffset;
                points = [start, [lane, start[1]], [lane, end[1]], end];
            } else if (fromPort === "right") {
                lane = Math.max(source.right, target.right) + laneOffset;
                points = [start, [lane, start[1]], [lane, end[1]], end];
            } else if (fromPort === "top") {
                lane = Math.max(source.top, target.top) + laneOffset;
                points = [start, [start[0], lane], [end[0], lane], end];
            } else {
                lane = Math.min(source.bottom, target.bottom) - laneOffset;
                points = [start, [start[0], lane], [end[0], lane], end];
            }
            return compactPoints(points);
        }

        if (start[0] === end[0] &&
            ((fromPort === "bottom" && toPort === "top" && start[1] > end[1]) ||
             (fromPort === "top" && toPort === "bottom" && start[1] < end[1]))) return [start, end];
        if (start[1] === end[1] &&
            ((fromPort === "right" && toPort === "left" && start[0] < end[0]) ||
             (fromPort === "left" && toPort === "right" && start[0] > end[0]))) return [start, end];

        if ((fromPort === "top" && toPort === "bottom") || (fromPort === "bottom" && toPort === "top")) {
            mid = (start[1] + end[1]) / 2;
            return compactPoints([start, [start[0], mid], [end[0], mid], end]);
        }
        if ((fromPort === "left" && toPort === "right") || (fromPort === "right" && toPort === "left")) {
            mid = (start[0] + end[0]) / 2;
            return compactPoints([start, [mid, start[1]], [mid, end[1]], end]);
        }

        if (fromPort === "left" || fromPort === "right") {
            corner = [end[0], start[1]];
            sourceOk = fromPort === "right" ? corner[0] > start[0] : corner[0] < start[0];
            targetOk = toPort === "top" ? corner[1] > end[1] : corner[1] < end[1];
            if (sourceOk && targetOk) return compactPoints([start, corner, end]);
            startOut = [start[0] + (fromPort === "right" ? CFG.GAP : -CFG.GAP), start[1]];
            endOut = [end[0], end[1] + (toPort === "top" ? CFG.GAP : -CFG.GAP)];
            return compactPoints([start, startOut, [startOut[0], endOut[1]], endOut, end]);
        }

        corner = [start[0], end[1]];
        sourceOk = fromPort === "top" ? corner[1] > start[1] : corner[1] < start[1];
        targetOk = toPort === "right" ? corner[0] > end[0] : corner[0] < end[0];
        if (sourceOk && targetOk) return compactPoints([start, corner, end]);
        startOut = [start[0], start[1] + (fromPort === "top" ? CFG.GAP : -CFG.GAP)];
        endOut = [end[0] + (toPort === "right" ? CFG.GAP : -CFG.GAP), end[1]];
        return compactPoints([start, startOut, [endOut[0], startOut[1]], endOut, end]);
    }

    function compactPoints(points) {
        var result = [], i, previous, a, b, c;
        for (i = 0; i < points.length; i++) {
            previous = result.length ? result[result.length - 1] : null;
            if (!previous || previous[0] !== points[i][0] || previous[1] !== points[i][1]) result.push(points[i]);
        }
        i = 1;
        while (i < result.length - 1) {
            a = result[i - 1]; b = result[i]; c = result[i + 1];
            if ((a[0] === b[0] && b[0] === c[0] && (b[1] - a[1]) * (c[1] - b[1]) >= 0) ||
                (a[1] === b[1] && b[1] === c[1] && (b[0] - a[0]) * (c[0] - b[0]) >= 0)) result.splice(i, 1);
            else i++;
        }
        return result;
    }

    function edgeLabelPoint(edge, points, source, fromPort, toPort, fontSize, font) {
        var ink=measureContainerTitle(edge.label,fontSize,font);
        if (edge.labelSegment !== undefined) {
            var segment = Math.min(edge.labelSegment, points.length - 2);
            var x = (points[segment][0] + points[segment + 1][0]) / 2;
            var y = (points[segment][1] + points[segment + 1][1]) / 2;
            if (edge.labelSide === "below") y -= ink.h/2+3;
            else if (edge.labelSide === "left") x -= ink.w/2+3;
            else if (edge.labelSide === "right") x += ink.w/2+3;
            else y += ink.h/2+3;
            return [x, y];
        }
        var position = edge.labelPosition || (source.shape === "decision" ? "source" : "middle");
        if (position === "source") return offsetLabel(points[0], fromPort, false, edge.labelSide);
        if (position === "target") return offsetLabel(points[points.length - 1], toPort, true, edge.labelSide);
        var best = 0, bestLength = -1, i, dx, dy, length;
        for (i = 0; i < points.length - 1; i++) {
            dx = points[i + 1][0] - points[i][0]; dy = points[i + 1][1] - points[i][1];
            length = Math.abs(dx) + Math.abs(dy);
            if (length > bestLength) { best = i; bestLength = length; }
        }
        return [(points[best][0] + points[best + 1][0]) / 2 + (points[best][0] === points[best + 1][0] ? 5 : 0),
                (points[best][1] + points[best + 1][1]) / 2 + (points[best][1] === points[best + 1][1] ? 5 : 0)];
    }

    function offsetLabel(point, port, targetSide, labelSide) {
        var x = point[0], y = point[1];
        if (labelSide === "left") return [x - 10, y];
        if (labelSide === "right") return [x + 10, y];
        if (labelSide === "above") return [x, y + 6];
        if (labelSide === "below") return [x, y - 6];
        if (port === "left") return [x - 6, y + 5];
        if (port === "right") return [x + 6, y + 5];
        if (port === "bottom") return [x + 6, y - 4];
        return [x + 6, y + (targetSide ? 4 : 5)];
    }

    function lineStyleDashes(lineStyle) {
        if (lineStyle === "dashed") return [4, 3];
        if (lineStyle === "dotted") return [2];
        return [];
    }

    function addLine(targetLayer, points, stroke, all, lineStyle) {
        var p = targetLayer.pathItems.add();
        p.setEntirePath(points); p.stroked = true; p.strokeColor = stroke; p.strokeWidth = CFG.STROKE; p.filled = false;
        var dashes = lineStyleDashes(lineStyle);
        try { p.strokeDashes = dashes; } catch (ignoreDash) {}
        p.name = "AI_FLOW_LINE"; all.push(p); return p;
    }

    function arrowLinePoints(points) {
        return trimArrowedPoints(points, false, true);
    }

    function addArrowedLine(targetLayer, points, stroke, all) {
        addRoutedLine(targetLayer, points, "end", stroke, all);
    }

    function trimArrowedPoints(points, startArrow, endArrow) {
        var result = [], i, first, second, last, previous, dx, dy, len, offset = CFG.ARROW_H / 2;
        for (i = 0; i < points.length; i++) result.push([points[i][0], points[i][1]]);
        if (startArrow) {
            first = result[0]; second = result[1]; dx = second[0] - first[0]; dy = second[1] - first[1]; len = Math.sqrt(dx * dx + dy * dy);
            result[0] = [first[0] + dx / len * offset, first[1] + dy / len * offset];
        }
        if (endArrow) {
            last = result[result.length - 1]; previous = result[result.length - 2];
            dx = last[0] - previous[0]; dy = last[1] - previous[1]; len = Math.sqrt(dx * dx + dy * dy);
            result[result.length - 1] = [last[0] - dx / len * offset, last[1] - dy / len * offset];
        }
        return compactPoints(result);
    }

    function addRoutedLine(targetLayer, points, arrowMode, stroke, all, lineStyle) {
        var startArrow = arrowMode === "start" || arrowMode === "both";
        var endArrow = arrowMode === "end" || arrowMode === "both";
        var first = points[0], second = points[1], last = points[points.length - 1], previous = points[points.length - 2];
        addLine(targetLayer, trimArrowedPoints(points, startArrow, endArrow), stroke, all, lineStyle);
        if (startArrow) addArrow(targetLayer, first[0], first[1], first[0] - second[0], first[1] - second[1], stroke, all);
        if (endArrow) addArrow(targetLayer, last[0], last[1], last[0] - previous[0], last[1] - previous[1], stroke, all);
    }

    function addArrow(targetLayer, tipX, tipY, dx, dy, fill, all) {
        var len = Math.sqrt(dx * dx + dy * dy), ux = dx / len, uy = dy / len, px = -uy, py = ux;
        var baseX = tipX - ux * CFG.ARROW_H, baseY = tipY - uy * CFG.ARROW_H;
        var p = targetLayer.pathItems.add();
        p.setEntirePath([
            [baseX - px * CFG.ARROW_W / 2, baseY - py * CFG.ARROW_W / 2],
            [baseX + ux * CFG.ARROW_NOTCH, baseY + uy * CFG.ARROW_NOTCH],
            [baseX + px * CFG.ARROW_W / 2, baseY + py * CFG.ARROW_W / 2],
            [tipX, tipY]
        ]);
        p.closed = true; p.stroked = false; p.filled = true; p.fillColor = fill; p.name = "AI_FLOW_ARROW5"; all.push(p);
    }

    function addEdgeLabel(label, x, y, all, fontSize, font, fill, vertical) {
        var tf = createText(String(label), x, y, fontSize, font, fill, vertical === true);
        tf.name = "AI_FLOW_EDGE_LABEL"; all.push(tf);
    }

    function freePoint(layout, xr, yr) {
        return [(layout.overlayLeft !== undefined ? layout.overlayLeft : layout.left) + xr * (layout.overlayWidth || layout.width),
                (layout.overlayTop !== undefined ? layout.overlayTop : layout.top) - yr * (layout.overlayHeight || layout.height)];
    }

    function drawFreeLines(items, layout, targetLayer, stroke, all) {
        var i, it, p1, p2;
        for (i = 0; i < items.length; i++) {
            it = items[i]; p1 = freePoint(layout, it.x1, it.y1); p2 = freePoint(layout, it.x2, it.y2);
            addRoutedLine(targetLayer, [p1, p2], it.arrow || "none", stroke, all, it.lineStyle);
        }
    }

    function drawFreeDots(items, layout, targetLayer, fill, all) {
        var i, j, it, count, p1, p2, x, y, dot, r;
        for (i = 0; i < items.length; i++) {
            it = items[i]; count = it.count || 18; p1 = freePoint(layout, it.x1, it.y1); p2 = freePoint(layout, it.x2, it.y2); r = it.radius || 1.2;
            for (j = 0; j < count; j++) {
                x = p1[0] + (p2[0] - p1[0]) * (count === 1 ? 0 : j / (count - 1)); y = p1[1] + (p2[1] - p1[1]) * (count === 1 ? 0 : j / (count - 1));
                dot = targetLayer.pathItems.ellipse(y + r, x - r, r * 2, r * 2); dot.stroked = false; dot.filled = true; dot.fillColor = fill; dot.name = "AI_FLOW_FREE_DOT"; all.push(dot);
            }
        }
    }

    function drawFreeTexts(items, layout, targetLayer, fill, all) {
        var i, it, made;
        for (i = 0; i < items.length; i++) {
            it = items[i]; made = createFreeText(it,
                (layout.overlayLeft !== undefined ? layout.overlayLeft : layout.left) + it.xr * (layout.overlayWidth || layout.width),
                (layout.overlayTop !== undefined ? layout.overlayTop : layout.top) - it.yr * (layout.overlayHeight || layout.height),
                layout.fontSize, fill);
            made.name = "AI_FLOW_FREE_TEXT"; all.push(made);
        }
    }

    function createFreeText(item, ax, ay, size, fill) {
        var rich = parseRichText(item.t, item.vertical === true), tf = doc.textFrames.add(), attr, b, w, cx, italic = item.italic === true || item.style === "italic";
        tf.contents = rich.text; attr = tf.textRange.characterAttributes; attr.size = size; attr.fillColor = fill; attr.autoLeading = true;
        try { attr.textFont = italic ? findFont(CFG.MATH_FONTS) : resolveFont().font; } catch (ignore) {}
        try { attr.italics = italic; } catch (ignore2) {}
        applyRichStyles(tf, rich, italic, item.subItalic === true || item.subStyle === "italic");
        tf.textRange.paragraphAttributes.justification = item.align === "left" ? Justification.LEFT : (item.align === "right" ? Justification.RIGHT : Justification.CENTER);
        b = tf.visibleBounds; w = b[2] - b[0]; cx = item.align === "left" ? ax + w / 2 : (item.align === "right" ? ax - w / 2 : ax);
        centerText(tf, cx, ay); return tf;
    }

    function createText(contents, cx, cy, size, font, fill, vertical) {
        var rich = parseRichText(String(contents), vertical === true);
        var tf = doc.textFrames.add();
        tf.contents = rich.text;
        var attr = tf.textRange.characterAttributes;
        attr.size = size; attr.fillColor = fill;
        attr.autoLeading = size !== 6;
        if (size === 6) attr.leading = CFG.LEADING_6;
        if (font) try { attr.textFont = font; } catch (ignore) {}
        applyRichStyles(tf, rich, false, false);
        try { tf.textRange.paragraphAttributes.justification = Justification.CENTER; } catch (ignore2) {}
        centerText(tf, cx, cy); return tf;
    }

    function parseRichText(s, vertical) {
        var subMap = { "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9" };
        var supMap = { "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "ⁿ": "n" };
        var greek = { alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ε", theta: "θ", lambda: "λ", mu: "μ", pi: "π", rho: "ρ", sigma: "σ", tau: "τ", phi: "φ", omega: "ω" };
        var out = "", subs = [], sups = [], italics = [], hasMath = false, math = false, i, ch;
        for (i = 0; i < s.length; i++) {
            ch = s.charAt(i);
            if (ch === "$") { math = !math; hasMath = true; continue; }
            if (ch === "\\" && i + 1 < s.length && /[A-Za-z]/.test(s.charAt(i + 1))) { var name = ""; while (i + 1 < s.length && /[A-Za-z]/.test(s.charAt(i + 1))) { i++; name += s.charAt(i); } appendRich(greek[name] || ("\\" + name), false, false, math); hasMath = true; continue; }
            if ((ch === "_" || ch === "^") && i + 1 < s.length) { i = appendScriptRun(s, i, ch === "_", math); hasMath = true; continue; }
            if (subMap[ch] !== undefined) { appendRich(subMap[ch], true, false, false); hasMath = true; continue; }
            if (supMap[ch] !== undefined) { appendRich(supMap[ch], false, true, false); hasMath = true; continue; }
            appendRich(ch, false, false, math);
        }
        return { text: out, subs: subs, sups: sups, italics: italics, hasMath: hasMath };
        function appendScriptRun(src, pos, isSub, inMath) {
            var j = pos + 1, chars = "";
            if (src.charAt(j) === "{") {
                j++;
                while (j < src.length && src.charAt(j) !== "}") { chars += src.charAt(j); j++; }
                pos = j < src.length ? j : j - 1;
            } else if (/[A-Za-z0-9]/.test(src.charAt(j))) {
                while (j < src.length && /[A-Za-z0-9]/.test(src.charAt(j))) { chars += src.charAt(j); j++; }
                pos = j - 1;
            } else {
                chars = src.charAt(j); pos = j;
            }
            for (var k = 0; k < chars.length; k++) appendRich(chars.charAt(k), isSub, !isSub, inMath);
            return pos;
        }
        function appendRich(value, sub, sup, inMath) {
            if (vertical && out.length > 0 && value !== "\r" && out.charAt(out.length - 1) !== "\r") { out += "\r"; subs.push(false); sups.push(false); italics.push(false); }
            out += value; subs.push(sub); sups.push(sup); italics.push(inMath && isMathItalicChar(value));
        }
        function isMathItalicChar(value) { return /[A-Za-zαβγδεθλμπρστφω]/.test(value); }
    }

    function applyRichStyles(tf, rich, forceItalic, subItalic) {
        var i, attr, italicFont = findFont(CFG.MATH_FONTS), uprightFont = findFont(CFG.MATH_SUB_FONTS);
        for (i = 0; i < rich.text.length; i++) try {
            attr = tf.textRange.characters[i].characterAttributes;
            if (rich.subs[i]) attr.baselinePosition = FontBaselineOption.SUBSCRIPT;
            if (rich.sups[i]) attr.baselinePosition = FontBaselineOption.SUPERSCRIPT;
            if (rich.subs[i] || rich.sups[i]) {
                attr.textFont = (subItalic || rich.italics[i]) ? italicFont : uprightFont;
                attr.italics = subItalic === true || rich.italics[i] === true;
            } else if (forceItalic || rich.italics[i]) {
                attr.textFont = italicFont;
                attr.italics = true;
            }
        } catch (ignore) {}
    }

    function centerText(tf, cx, cy) {
        var outline = tf.duplicate().createOutline(), b;
        try { b = [outline.visibleBounds[0], outline.visibleBounds[1], outline.visibleBounds[2], outline.visibleBounds[3]]; }
        finally { outline.remove(); }
        tf.translate(cx - (b[0] + b[2]) / 2, cy - (b[1] + b[3]) / 2);
    }

    function measureContainerTitle(contents, size, font) {
        var tf = createText(contents, 0, 0, size, font, gray(100)), outline = null, b;
        try { outline = tf.duplicate().createOutline(); b = outline.visibleBounds; return {w:b[2]-b[0],h:b[1]-b[3]}; }
        finally { if (outline) outline.remove(); tf.remove(); }
    }

    function measureText(contents, size, font) { return measureContainerTitle(contents, size, font); }

    function displayText(value, vertical) {
        var text = String(value).replace(/\r\n/g, "\r").replace(/\n/g, "\r");
        if (!vertical) return text;
        text = text.replace(/\r/g, "");
        var out = [], i;
        for (i = 0; i < text.length; i++) out.push(text.charAt(i));
        return out.join("\r");
    }

    function resolveFont() {
        var composite = findFont(["\u73b0 \u5b8b\u4f53 1"]);
        if (composite) return { font: composite, composite: true };
        return { font: findFont(["SimSun", "\u5b8b\u4f53"]), composite: false };
    }

    function findFont(names) {
        var i;
        for (i = 0; i < names.length; i++) try { return app.textFonts.getByName(names[i]); } catch (ignore) {}
        return null;
    }

    function gray(value) { var c = new GrayColor(); c.gray = value; return c; }
    function isFiniteNumber(value) { return typeof value === "number" && isFinite(value); }

    function parseInputData(text) {
        var raw = String(text).replace(/^\uFEFF/, "");
        try {
            var parsed = parseStrictJson(raw);
            if (parsed && !parsed.kind && parsed.charts instanceof Array) {
                parsed.schemaVersion = 3;
                parsed.kind = "statChart";
            }
            return parsed;
        } catch (jsonError) {
            var chart = parseChartSpecText(raw);
            if (chart) return chart;
            throw jsonError;
        }
    }

    function parseChartSpecText(text) {
        var cleaned = String(text).replace(/^\uFEFF/, "")
            .replace(/```[a-zA-Z]*/g, "").replace(/```/g, "")
            .replace(/\/\/[^\n]*/g, "");
        if (cleaned.indexOf("charts") < 0 && cleaned.indexOf("SPEC") < 0) return null;
        var body = cleaned.replace(/^\s*var\s+SPEC\s*=\s*/, "").replace(/;\s*$/, "");
        var spec = eval("(" + body + ")");
        if (!spec || !(spec.charts instanceof Array)) return null;
        return { schemaVersion: 3, kind: "statChart", charts: spec.charts, cols: spec.cols, renderMode: spec.renderMode, textOnly: spec.textOnly };
    }

    function drawStatChart(root) {
        var ab = doc.artboards[doc.artboards.getActiveArtboardIndex()].artboardRect;
        var left = ab[0] + CFG.MARGIN, top = ab[1] - CFG.MARGIN;
        var width = ab[2] - ab[0] - CFG.MARGIN * 2, height = ab[1] - ab[3] - CFG.MARGIN * 2;
        var cols = root.cols || Math.ceil(Math.sqrt(root.charts.length));
        var rows = Math.ceil(root.charts.length / cols), gap = 24;
        var panelW = (width - gap * (cols - 1)) / cols;
        var panelH = (height - gap * (rows - 1)) / rows;
        var fontInfo = resolveFont(), size = root.fontSize || 8, all = [], i, row, col;
        for (i = 0; i < root.charts.length; i++) {
            row = Math.floor(i / cols); col = i % cols;
            drawStatTextPanel(root.charts[i], left + col * (panelW + gap), top - row * (panelH + gap), panelW, panelH, size, fontInfo.font, gray(0), all);
        }
        doc.selection = null;
        for (i = 0; i < all.length; i++) all[i].selected = true;
        alert("流程图生成器 3.0 已生成：" + root.charts.length + " 个统计图文字面板。\n未绘制坐标轴、网格、折线、柱、点、阴影带或箱线图。");
    }

    function drawStatTextPanel(ch, left, top, width, height, size, font, fill, all) {
        var plotLeft = left + 44, plotRight = left + width - 8, plotTop = top - 18, plotBottom = top - height + 30;
        var plotW = plotRight - plotLeft, plotH = plotTop - plotBottom;
        var yTicks = statTicks(ch), xTicks = statXTicks(ch), i, tf, y, x, legendY;
        function add(text, cx, cy) {
            var item = createText(text, cx, cy, size, font, fill);
            item.name = "AI_FLOW_STAT_TEXT"; all.push(item); return item;
        }
        add(ch.title || "", plotLeft + plotW / 2, top - 4);
        if (ch.yLabel) {
            tf = add(statUnitLabel(ch.yLabel), left + 9, plotBottom + plotH / 2);
            try { tf.rotate(90); } catch (ignoreRotate) {}
        }
        for (i = 0; i < yTicks.length; i++) {
            y = yTicks.length === 1 ? plotBottom + plotH / 2 : plotBottom + plotH * i / (yTicks.length - 1);
            add(statFormatNumber(yTicks[i]), plotLeft - 12, y);
        }
        for (i = 0; i < xTicks.length; i++) {
            x = xTicks.length === 1 ? plotLeft + plotW / 2 : plotLeft + plotW * i / (xTicks.length - 1);
            add(xTicks[i], x, plotBottom - 13);
        }
        if (ch.xLabel) add(statUnitLabel(ch.xLabel), plotLeft + plotW / 2, plotBottom - 34);
        if (ch.y2Label) {
            tf = add(statUnitLabel(ch.y2Label), plotRight + 10, plotBottom + plotH / 2);
            try { tf.rotate(-90); } catch (ignoreRotate2) {}
        }
        if (ch.y2Ticks instanceof Array) for (i = 0; i < ch.y2Ticks.length; i++) {
            y = ch.y2Ticks.length === 1 ? plotBottom + plotH / 2 : plotBottom + plotH * i / (ch.y2Ticks.length - 1);
            add(statFormatNumber(ch.y2Ticks[i]), plotRight + 12, y);
        }
        if (ch.series instanceof Array) for (i = 0; i < ch.series.length; i++) {
            if (!ch.series[i].name) continue;
            legendY = plotTop - 10 - i * (size + 4);
            add(ch.series[i].name, plotRight - 4, legendY);
        }
        if (ch.annotation) add(ch.annotation, plotRight - 4, plotTop - 10 - (ch.series ? ch.series.length : 0) * (size + 4) - 10);
        if (ch.annots instanceof Array) for (i = 0; i < ch.annots.length; i++) {
            add(String(ch.annots[i].t), plotLeft + plotW * (ch.annots[i].xr === undefined ? 0.5 : ch.annots[i].xr), plotBottom + plotH * (ch.annots[i].yr === undefined ? 0.5 : ch.annots[i].yr));
        }
    }

    function statTicks(ch) {
        var values = [], i, step;
        if (ch.yTicks instanceof Array && ch.yTicks.length) return ch.yTicks;
        for (step = ch.yMin, i = 0; step <= ch.yMax + ch.yStep * 0.5 && i < 1000; step += ch.yStep, i++) values.push(step);
        return values;
    }

    function statXTicks(ch) {
        var values = [], i;
        if ((ch.type === "bar" || ch.type === "box" || ch.type === "boxplot") && ch.xCats instanceof Array) return ch.xCats;
        if (!(ch.xTicks instanceof Array)) return values;
        for (i = 0; i < ch.xTicks.length; i++) values.push(ch.xTickLabels && ch.xTickLabels[i] !== undefined ? ch.xTickLabels[i] : statFormatNumber(ch.xTicks[i]));
        return values;
    }

    function statUnitLabel(text) {
        var value = String(text), match = value.match(/^(.*)\s*\(([^()]*)\)$/);
        return match ? match[1] + "/" + match[2] : value;
    }

    function statFormatNumber(value) { return String(value); }

    function validateStatChart(root) {
        validateChartRenderMode(root, "statChart");
        if (root.schemaVersion !== 3) throw "statChart 需要 schemaVersion 3。";
        if (!(root.charts instanceof Array) || root.charts.length === 0) throw "statChart 必须有非空 charts 数组。";
        if (root.cols !== undefined && (!isFiniteNumber(root.cols) || Math.floor(root.cols) !== root.cols || root.cols < 1)) throw "statChart.cols 必须是正整数。";
        var i;
        for (i = 0; i < root.charts.length; i++) validateChart(root.charts[i], i + 1);
    }

    function validateChart(ch, index) {
        validateChartRenderMode(ch, "chart " + index);
        if (!ch || typeof ch !== "object") throw "chart " + index + " 必须是对象。";
        if (typeof ch.title !== "string") throw "chart " + index + " 缺少 title。";
        if (typeof ch.yLabel !== "string") throw "chart " + index + " 缺少 yLabel。";
        var hasTicks = ch.yTicks instanceof Array && ch.yTicks.length > 0;
        var hasRange = isFiniteNumber(ch.yMin) && isFiniteNumber(ch.yMax) && isFiniteNumber(ch.yStep);
        if (!hasTicks && !hasRange) throw "chart " + index + " 必须提供 yTicks 或 yMin/yMax/yStep。";
        if (hasTicks) for (var yt = 0; yt < ch.yTicks.length; yt++) if (!isFiniteNumber(ch.yTicks[yt])) throw "chart " + index + " yTicks 必须全部是数字。";
        if (hasTicks && ch.yTicks.length < 2 && !hasRange) throw "chart " + index + " 绘制数据时至少需要两项 yTicks，或提供 yMin/yMax/yStep。";
        if (hasRange && ch.yMax <= ch.yMin) throw "chart " + index + " 的 yMax 必须大于 yMin。";
        if (hasRange && ch.yStep <= 0) throw "chart " + index + " 的 yStep 必须为正数。";
        validateChartLines(ch, index);
        if (ch.type === "bar") {
            if (!(ch.xCats instanceof Array) || ch.xCats.length === 0) throw "chart " + index + " 柱状图需要 xCats。";
            validateChartSeries(ch, ch.xCats.length, index);
        } else if (ch.type === "box" || ch.type === "boxplot") {
            if (!(ch.xCats instanceof Array) || ch.xCats.length === 0) throw "chart " + index + " 箱线图需要 xCats。";
            if (!(ch.boxes instanceof Array) || ch.boxes.length !== ch.xCats.length) throw "chart " + index + " boxes 数量必须等于 xCats。";
            var b;
            for (b = 0; b < ch.boxes.length; b++) validateBox(ch.boxes[b], index, b + 1);
        } else {
            if (ch.type !== undefined && ch.type !== "line") throw "chart " + index + " 不支持 type：" + ch.type;
            if (!(ch.xTicks instanceof Array) || ch.xTicks.length === 0) throw "chart " + index + " 折线图需要 xTicks。";
            var xt;
            for (xt = 0; xt < ch.xTicks.length; xt++) {
                if (!isFiniteNumber(ch.xTicks[xt])) throw "chart " + index + " xTicks must be numeric; use xTickLabels for category text.";
            }
            if (ch.xTickLabels !== undefined) {
                if (!(ch.xTickLabels instanceof Array) || ch.xTickLabels.length !== ch.xTicks.length) throw "chart " + index + " xTickLabels length must match xTicks.";
                for (xt = 0; xt < ch.xTickLabels.length; xt++) if (typeof ch.xTickLabels[xt] !== "string") throw "chart " + index + " xTickLabels must be strings.";
            }
            validateChartSeries(ch, ch.xTicks.length, index);
            if (ch.band !== undefined) validateBand(ch.band, ch.xTicks.length, index, "band");
        }
    }

    function validateChartRenderMode(item, label) {
        if (item.renderMode !== undefined && item.renderMode !== "textOnly" && item.renderMode !== "plot") throw label + " renderMode 只能是 textOnly 或 plot。";
        if (item.textOnly !== undefined && typeof item.textOnly !== "boolean") throw label + " textOnly 必须是布尔值。";
    }

    function validateChartSeries(ch, expected, chartIndex) {
        if (!(ch.series instanceof Array)) throw "chart " + chartIndex + " 缺少 series。";
        var i, ser;
        for (i = 0; i < ch.series.length; i++) {
            ser = ch.series[i];
            if (!ser || typeof ser !== "object") throw "chart " + chartIndex + " series " + (i + 1) + " 必须是对象。";
            if (ser.name !== undefined && typeof ser.name !== "string") throw "chart " + chartIndex + " series " + (i + 1) + " name 必须是字符串。";
            if (ser.data !== undefined) validateArrayLength(ser.data, expected, "chart " + chartIndex + " series " + (i + 1) + " data");
            validateOptionalArray(ser.error, expected, "chart " + chartIndex + " series " + (i + 1) + " error");
            validateOptionalArray(ser.err, expected, "chart " + chartIndex + " series " + (i + 1) + " err");
            validateOptionalArray(ser.errors, expected, "chart " + chartIndex + " series " + (i + 1) + " errors");
            validateOptionalArray(ser.errorLow, expected, "chart " + chartIndex + " series " + (i + 1) + " errorLow");
            validateOptionalArray(ser.errorHigh, expected, "chart " + chartIndex + " series " + (i + 1) + " errorHigh");
            validateOptionalArray(ser.labels, expected, "chart " + chartIndex + " series " + (i + 1) + " labels");
            validateOptionalArray(ser.valueLabels, expected, "chart " + chartIndex + " series " + (i + 1) + " valueLabels");
            if (ser.band !== undefined) validateBand(ser.band, expected, chartIndex, "series " + (i + 1) + " band");
        }
    }

    function validateChartLines(ch, chartIndex) {
        var list = ch.thresholds || ch.hLines, i, item;
        if (list === undefined) return;
        if (!(list instanceof Array)) throw "chart " + chartIndex + " thresholds 必须是数组。";
        for (i = 0; i < list.length; i++) {
            item = list[i];
            if (typeof item === "number") continue;
            if (!item || !isFiniteNumber(item.y)) throw "chart " + chartIndex + " threshold " + (i + 1) + " 缺少数字 y。";
            if (item.label !== undefined && typeof item.label !== "string") throw "chart " + chartIndex + " threshold " + (i + 1) + " label 必须是字符串。";
        }
    }

    function validateBand(band, expected, chartIndex, name) {
        if (!band || typeof band !== "object") throw "chart " + chartIndex + " " + name + " 必须是对象。";
        validateArrayLength(band.low, expected, "chart " + chartIndex + " " + name + ".low");
        validateArrayLength(band.high, expected, "chart " + chartIndex + " " + name + ".high");
    }

    function validateBox(box, chartIndex, boxIndex) {
        var values;
        if (box instanceof Array) values = box;
        else if (box && typeof box === "object") values = [box.min, box.q1, box.median, box.q3, box.max];
        else throw "chart " + chartIndex + " box " + boxIndex + " 无效。";
        if (values.length < 5) throw "chart " + chartIndex + " box " + boxIndex + " 缺少 min/q1/median/q3/max。";
        var i;
        for (i = 0; i < 5; i++) if (!isFiniteNumber(values[i])) throw "chart " + chartIndex + " box " + boxIndex + " 五数摘要必须是数字。";
    }

    function validateOptionalArray(value, expected, name) {
        if (value === undefined || typeof value === "number") return;
        validateArrayLength(value, expected, name);
    }

    function validateArrayLength(value, expected, name) {
        if (!(value instanceof Array)) throw name + " 必须是数组。";
        if (value.length !== expected) throw name + " 长度必须等于 " + expected + "。";
    }

    function parseStrictJson(text) {
        var cleaned = String(text).replace(/^\uFEFF/, "").replace(/^\s*```json\s*/i, "").replace(/\s*```\s*$/, "");
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(cleaned);
        var safe = cleaned.replace(/\\["\\\/bfnrtu]/g, "@").replace(/"[^"\\\n\r]*"|true|false|null|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?/g, "]").replace(/(?:^|:|,)(?:\s*\[)+/g, "");
        if (!/^[\],:{}\s]*$/.test(safe)) throw "不是严格 JSON；请勿使用 var SPEC、注释或尾逗号。";
        return eval("(" + cleaned + ")");
    }

    function askJson(defaultText) {
        var dlg = new Window("dialog", "AI流程图生成器 3.0 — JSON");
        dlg.alignChildren = "fill";
        dlg.add("statictext", undefined, "粘贴 illustrator-flowchart Skill 生成的纯 JSON；流程图/自由图/统计图都从这里生成：");
        var ed = dlg.add("edittext", [0, 0, 640, 430], defaultText, { multiline: true, scrolling: true });
        try { ed.graphics.font = ScriptUI.newFont("Consolas", "Regular", 11); } catch (ignore) {}
        var buttons = dlg.add("group"); buttons.alignment = "right";
        var load = buttons.add("button", undefined, "加载 JSON…");
        buttons.add("button", undefined, "生成图", { name: "ok" });
        buttons.add("button", undefined, "取消", { name: "cancel" });
        load.onClick = function () {
            var file = File.openDialog("选择流程图 JSON", "Flowchart JSON:*.json;All files:*.*");
            if (!file) return;
            var text = readFile(file);
            if (text === null) alert("无法读取：" + file.fsName); else ed.text = text;
        };
        return dlg.show() === 1 ? ed.text : null;
    }

    function readSibling(name) {
        try { return readFile(new File(File($.fileName).parent.fsName + "\\" + name)); } catch (ignore) { return null; }
    }

    function readFile(file) {
        if (!file || !file.exists) return null;
        file.encoding = "UTF-8";
        if (!file.open("r")) return null;
        var text = file.read(); file.close(); return text;
    }
})();
