const customCSS = `
    ::-webkit-scrollbar {
        width: 10px;
    }
    ::-webkit-scrollbar-track {
        background: #27272a;
    }
    ::-webkit-scrollbar-thumb {
        background: #888;
        border-radius: 0.375rem;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #555;
    }
`;

const styleTag = document.createElement("style");
styleTag.textContent = customCSS;
document.head.append(styleTag);

let labels = [];

function unmarkPage() {
    // Unmark page logic
    for (const label of labels) {
        document.body.removeChild(label);
    }
    labels = [];
}

function markPage() {
    unmarkPage();

    var bodyRect = document.body.getBoundingClientRect();
    
    // 🆕 EXPANSÃO: Considerar dimensões completas da página
    var fullPageWidth = Math.max(
        document.documentElement.scrollWidth,
        document.documentElement.offsetWidth,
        document.documentElement.clientWidth,
        document.body.scrollWidth,
        document.body.offsetWidth,
        document.body.clientWidth
    );
    
    var fullPageHeight = Math.max(
        document.documentElement.scrollHeight,
        document.documentElement.offsetHeight,
        document.documentElement.clientHeight,
        document.body.scrollHeight,
        document.body.offsetHeight,
        document.body.clientHeight
    );

    // Viewport atual (para referência)
    var vw = Math.max(
        document.documentElement.clientWidth || 0,
        window.innerWidth || 0
    );
    var vh = Math.max(
        document.documentElement.clientHeight || 0,
        window.innerHeight || 0
    );

    var items = Array.prototype.slice
        .call(document.querySelectorAll("*"))
        .map(function (element) {
            var textualContent = element.textContent.trim().replace(/\s{2,}/g, " ");
            var elementType = element.tagName.toLowerCase();
            var ariaLabel = element.getAttribute("aria-label") || "";

            // 🆕 MODIFICAÇÃO: getBoundingClientRect pega posição absoluta na página
            var elementRect = element.getBoundingClientRect();
            var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            var scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;

            // Converter coordenadas relativas ao viewport para coordenadas absolutas da página
            var absoluteRect = {
                left: elementRect.left + scrollLeft,
                top: elementRect.top + scrollTop,
                right: elementRect.right + scrollLeft,
                bottom: elementRect.bottom + scrollTop,
                width: elementRect.width,
                height: elementRect.height
            };

            // 🆕 VERIFICAÇÃO EXPANDIDA: Elemento dentro dos limites da página completa
            var isInPageBounds = (
                absoluteRect.left >= 0 &&
                absoluteRect.top >= 0 &&
                absoluteRect.right <= fullPageWidth &&
                absoluteRect.bottom <= fullPageHeight &&
                absoluteRect.width > 0 &&
                absoluteRect.height > 0
            );

            // 🆕 DETECÇÃO MELHORADA: Verifica se elemento é realmente interativo
            var computedStyle = window.getComputedStyle(element);
            var isVisible = (
                computedStyle.display !== 'none' &&
                computedStyle.visibility !== 'hidden' &&
                computedStyle.opacity !== '0' &&
                element.offsetParent !== null
            );

            var rects = [];
            if (isInPageBounds && isVisible) {
                // Para elementos no viewport atual, usar detecção melhorada
                if (elementRect.left < vw && elementRect.top < vh && 
                    elementRect.right > 0 && elementRect.bottom > 0) {
                    
                    // Verificação de centro (só para elementos visíveis)
                    var center_x = elementRect.left + elementRect.width / 2;
                    var center_y = elementRect.top + elementRect.height / 2;
                    var elAtCenter = document.elementFromPoint(center_x, center_y);
                    
                    if (elAtCenter === element || element.contains(elAtCenter)) {
                        rects = [{
                            left: Math.max(0, absoluteRect.left),
                            top: Math.max(0, absoluteRect.top),
                            right: Math.min(fullPageWidth, absoluteRect.right),
                            bottom: Math.min(fullPageHeight, absoluteRect.bottom),
                            width: absoluteRect.width,
                            height: absoluteRect.height,
                            inViewport: true
                        }];
                    }
                } else {
                    // 🆕 Para elementos FORA do viewport, adicionar diretamente
                    rects = [{
                        left: Math.max(0, absoluteRect.left),
                        top: Math.max(0, absoluteRect.top),
                        right: Math.min(fullPageWidth, absoluteRect.right),
                        bottom: Math.min(fullPageHeight, absoluteRect.bottom),
                        width: absoluteRect.width,
                        height: absoluteRect.height,
                        inViewport: false
                    }];
                }
            }

            var area = rects.reduce((acc, rect) => acc + rect.width * rect.height, 0);

            return {
                element: element,
                include:
                    element.tagName === "INPUT" ||
                    element.tagName === "TEXTAREA" ||
                    element.tagName === "SELECT" ||
                    element.tagName === "BUTTON" ||
                    element.tagName === "A" ||
                    element.onclick != null ||
                    computedStyle.cursor == "pointer" ||
                    element.tagName === "IFRAME" ||
                    element.tagName === "VIDEO" ||
                    // 🆕 ADICIONAIS: Mais tipos de elementos interativos
                    element.tagName === "DETAILS" ||
                    element.tagName === "SUMMARY" ||
                    element.hasAttribute("onclick") ||
                    element.hasAttribute("role") && ["button", "link", "tab"].includes(element.getAttribute("role")),
                area,
                rects,
                text: textualContent,
                type: elementType,
                ariaLabel: ariaLabel,
                // 🆕 METADADOS EXTRAS
                absolutePosition: absoluteRect,
                isVisible: isVisible,
                inCurrentViewport: rects.length > 0 && rects[0].inViewport
            };
        })
        .filter((item) => item.include && item.area >= 20);

    // Only keep inner clickable items
    items = items.filter(
        (x) => !items.some((y) => x.element.contains(y.element) && !(x == y))
    );

    // Function to generate random colors
    function getRandomColor() {
        var letters = "0123456789ABCDEF";
        var color = "#";
        for (var i = 0; i < 6; i++) {
            color += letters[Math.floor(Math.random() * 16)];
        }
        return color;
    }

    // 🆕 VISUALIZAÇÃO EXPANDIDA: Marcar elementos visíveis E fora do viewport
    items.forEach(function (item, index) {
        item.rects.forEach((bbox) => {
            newElement = document.createElement("div");
            var borderColor = getRandomColor();
            
            // 🆕 Estilo diferente para elementos fora do viewport
            var isInViewport = bbox.inViewport;
            var borderStyle = isInViewport ? "2px dashed" : "3px dotted";
            var opacity = isInViewport ? "1" : "0.7";
            
            newElement.style.outline = `${borderStyle} ${borderColor}`;
            newElement.style.position = "absolute"; // 🆕 MUDANÇA: absolute para elementos fora do viewport
            newElement.style.left = bbox.left + "px";
            newElement.style.top = bbox.top + "px";
            newElement.style.width = bbox.width + "px";
            newElement.style.height = bbox.height + "px";
            newElement.style.pointerEvents = "none";
            newElement.style.boxSizing = "border-box";
            newElement.style.zIndex = 2147483647;
            newElement.style.opacity = opacity;

            // Add floating label at the corner
            var label = document.createElement("span");
            label.textContent = index + (isInViewport ? "" : "📍"); // 🆕 Emoji para elementos fora do viewport
            label.style.position = "absolute";
            label.style.top = "-19px";
            label.style.left = "0px";
            label.style.background = borderColor;
            label.style.color = "white";
            label.style.padding = "2px 4px";
            label.style.fontSize = "12px";
            label.style.borderRadius = "2px";
            label.style.fontWeight = isInViewport ? "normal" : "bold";
            newElement.appendChild(label);

            document.body.appendChild(newElement);
            labels.push(newElement);
        });
    });

    // 🆕 COORDENADAS EXPANDIDAS: Incluir posição absoluta e metadados
    const coordinates = items.flatMap((item, index) =>
        item.rects.map(({ left, top, width, height, inViewport }) => ({
            id: index,
            x: (left + left + width) / 2,
            y: (top + top + height) / 2,
            absoluteX: left + width / 2,
            absoluteY: top + height / 2,
            type: item.type,
            text: item.text,
            ariaLabel: item.ariaLabel,
            inViewport: inViewport,
            // 🆕 DADOS EXTRAS
            bbox: { left, top, width, height },
            scrollPosition: {
                x: window.pageXOffset || document.documentElement.scrollLeft,
                y: window.pageYOffset || document.documentElement.scrollTop
            },
            pageSize: {
                width: fullPageWidth,
                height: fullPageHeight
            },
            viewportSize: {
                width: vw,
                height: vh
            }
        }))
    );

    // 🆕 RELATÓRIO: Log informações úteis
    console.log(`📊 Elementos encontrados: ${items.length}`);
    console.log(`📱 No viewport: ${coordinates.filter(c => c.inViewport).length}`);
    console.log(`🌐 Fora do viewport: ${coordinates.filter(c => !c.inViewport).length}`);
    console.log(`📏 Página: ${fullPageWidth}x${fullPageHeight}px`);
    console.log(`👀 Viewport: ${vw}x${vh}px`);

    return coordinates;
}

// 🆕 FUNÇÃO EXTRA: Marcar apenas elementos fora do viewport
function markOffscreenElements() {
    const allCoords = markPage();
    const offscreenOnly = allCoords.filter(coord => !coord.inViewport);
    
    console.log(`🔍 Elementos fora do viewport: ${offscreenOnly.length}`);
    return offscreenOnly;
}

// 🆕 FUNÇÃO EXTRA: Rolar para elemento específico
function scrollToElement(elementId) {
    const coords = markPage();
    const element = coords.find(c => c.id === elementId);
    
    if (element) {
        window.scrollTo({
            left: element.absoluteX - window.innerWidth / 2,
            top: element.absoluteY - window.innerHeight / 2,
            behavior: 'smooth'
        });
        console.log(`🎯 Rolando para elemento ${elementId}: ${element.text.slice(0, 50)}...`);
    } else {
        console.log(`❌ Elemento ${elementId} não encontrado`);
    }
}