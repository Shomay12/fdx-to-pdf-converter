const fileInput = document.getElementById('fdxFile');
const convertBtn = document.getElementById('convertBtn');
const statusEl = document.getElementById('status');
const previewEl = document.getElementById('preview');
const titleEl = document.getElementById('title');
const authorEl = document.getElementById('author');

let parsedParagraphs = [];

function textFromParagraph(paragraphEl) {
  const textNodes = [...paragraphEl.querySelectorAll('Text')];
  if (!textNodes.length) return '';

  // Keep original text flow as-is (no whitespace collapsing), so
  // content is preserved exactly from FDX into PDF.
  return textNodes.map(t => t.textContent || '').join('');
}

function parseFDX(xmlText) {
  const parser = new DOMParser();
  const xml = parser.parseFromString(xmlText, 'text/xml');
  const err = xml.querySelector('parsererror');
  if (err) throw new Error('Invalid FDX/XML file.');

  // Preserve source order and avoid duplicate selection.
  const contentParas = [...xml.querySelectorAll('Content Paragraph')];
  const paraEls = contentParas.length ? contentParas : [...xml.querySelectorAll('Paragraph')];

  const paras = paraEls.map((p, idx) => ({
    index: idx,
    type: (p.getAttribute('Type') || 'Action').trim(),
    text: textFromParagraph(p)
  }));

  const hasAnyText = paras.some(p => (p.text || '').replace(/\s/g, '').length > 0);
  if (!hasAnyText) throw new Error('No screenplay content found in the FDX file.');

  return paras;
}

function buildPreview(paras) {
  const preview = paras.slice(0, 80).map(p => `[${p.type}] ${p.text}`).join('\n');
  return preview + (paras.length > 80 ? '\n\n... (truncated)' : '');
}

function getStyleForType(typeRaw, left) {
  const type = (typeRaw || '').toLowerCase();
  let x = left;
  let size = 11;
  let style = 'normal';

  if (type.includes('scene')) {
    x = left;
    style = 'bold';
  } else if (type.includes('character')) {
    x = left + 70;
    style = 'bold';
  } else if (type.includes('dialogue')) {
    x = left + 40;
    style = 'normal';
  } else if (type.includes('parenthetical')) {
    x = left + 55;
    size = 10;
    style = 'italic';
  } else if (type.includes('transition')) {
    x = left + 120;
    style = 'bold';
  }

  return { x, size, style };
}

function wrapParagraphLines(doc, text, maxWidth) {
  const logicalLines = String(text ?? '').split(/\r?\n/);
  const wrapped = [];

  logicalLines.forEach(line => {
    if (line === '') {
      wrapped.push('');
      return;
    }
    const pieces = doc.splitTextToSize(line, maxWidth);
    if (Array.isArray(pieces) && pieces.length) wrapped.push(...pieces);
    else wrapped.push('');
  });

  return wrapped.length ? wrapped : [''];
}

function generatePDF(paragraphs) {
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });

  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const left = 20;
  const top = 20;
  const bottom = 20;
  const width = pageW - 40;
  const lineHeight = 5.3;
  const paraGap = 1.2;

  const title = titleEl.value.trim() || 'Screenplay';
  const author = authorEl.value.trim() || 'Unknown Author';

  doc.setFont('courier', 'bold');
  doc.setFontSize(16);
  doc.text(title, pageW / 2, 35, { align: 'center' });
  doc.setFont('courier', 'normal');
  doc.setFontSize(11);
  doc.text(`by ${author}`, pageW / 2, 43, { align: 'center' });

  let y = 55;

  paragraphs.forEach((p) => {
    const { x, size, style } = getStyleForType(p.type, left);
    doc.setFont('courier', style);
    doc.setFontSize(size);

    const availableWidth = Math.max(20, width - (x - left));
    const lines = wrapParagraphLines(doc, p.text, availableWidth);
    const requiredHeight = lines.length * lineHeight + paraGap;

    // Page break BEFORE drawing, so text never gets cut/shifted.
    if (y + requiredHeight > pageH - bottom) {
      doc.addPage();
      y = top;
    }

    doc.text(lines, x, y);
    y += requiredHeight;
  });

  const safeTitle = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'screenplay';
  doc.save(`${safeTitle}.pdf`);
}

fileInput.addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;

  statusEl.textContent = 'Reading file...';
  try {
    const text = await file.text();
    parsedParagraphs = parseFDX(text);
    previewEl.textContent = buildPreview(parsedParagraphs);
    statusEl.textContent = `Loaded ${parsedParagraphs.length} blocks from ${file.name}.`;

    if (!titleEl.value.trim()) titleEl.value = file.name.replace(/\.fdx$/i, '');
  } catch (err) {
    parsedParagraphs = [];
    previewEl.textContent = 'Could not parse file.';
    statusEl.textContent = err.message;
  }
});

convertBtn.addEventListener('click', () => {
  if (!parsedParagraphs.length) {
    statusEl.textContent = 'Please upload a valid .fdx file first.';
    return;
  }
  statusEl.textContent = 'Generating PDF...';
  setTimeout(() => {
    generatePDF(parsedParagraphs);
    statusEl.textContent = 'Done! PDF downloaded.';
  }, 50);
});
