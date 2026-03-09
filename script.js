const fileInput = document.getElementById('fdxFile');
const convertBtn = document.getElementById('convertBtn');
const statusEl = document.getElementById('status');
const previewEl = document.getElementById('preview');
const titleEl = document.getElementById('title');
const authorEl = document.getElementById('author');

let parsedParagraphs = [];

function textFromParagraph(p) {
  const chunks = [...p.querySelectorAll('Text')].map(t => t.textContent || '');
  return chunks.join('').replace(/\s+/g, ' ').trim();
}

function parseFDX(xmlText) {
  const parser = new DOMParser();
  const xml = parser.parseFromString(xmlText, 'text/xml');
  const err = xml.querySelector('parsererror');
  if (err) throw new Error('Invalid FDX/XML file.');

  const paras = [...xml.querySelectorAll('Content > Paragraph, Paragraph')].map(p => ({
    type: (p.getAttribute('Type') || 'Action').trim(),
    text: textFromParagraph(p)
  })).filter(p => p.text.length > 0);

  if (!paras.length) throw new Error('No screenplay content found in the FDX file.');
  return paras;
}

function buildPreview(paras) {
  return paras.slice(0, 80).map(p => `[${p.type}] ${p.text}`).join('\n') + (paras.length > 80 ? '\n\n... (truncated)' : '');
}

function drawParagraph(doc, p, y, left, width) {
  const type = p.type.toLowerCase();
  let x = left;
  let size = 11;

  if (type.includes('scene')) {
    x = left;
    size = 11;
    doc.setFont('courier', 'bold');
  } else if (type.includes('character')) {
    x = left + 70;
    size = 11;
    doc.setFont('courier', 'bold');
  } else if (type.includes('dialogue')) {
    x = left + 40;
    size = 11;
    doc.setFont('courier', 'normal');
  } else if (type.includes('parenthetical')) {
    x = left + 55;
    size = 10;
    doc.setFont('courier', 'italic');
  } else if (type.includes('transition')) {
    x = left + 120;
    size = 11;
    doc.setFont('courier', 'bold');
  } else {
    x = left;
    size = 11;
    doc.setFont('courier', 'normal');
  }

  doc.setFontSize(size);
  const lines = doc.splitTextToSize(p.text, width - (x - left));
  doc.text(lines, x, y);
  return y + lines.length * 5.3 + 1.2;
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
    y = drawParagraph(doc, p, y, left, width);
    if (y > pageH - bottom) {
      doc.addPage();
      y = top;
    }
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
