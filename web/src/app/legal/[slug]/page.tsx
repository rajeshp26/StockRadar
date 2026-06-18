import Link from 'next/link';
import fs from 'fs';
import path from 'path';

interface LegalPageProps {
  params: Promise<{ slug: string }>;
}

const TITLES: Record<string, string> = {
  terms: 'Terms of Service',
  privacy: 'Privacy Policy',
};

function renderMarkdown(md: string): string {
  const lines = md.split('\n');
  let html = '';
  let inList = false;

  for (const line of lines) {
    if (line.startsWith('# ')) {
      html += `<h1 class="text-3xl font-black mb-2">${line.slice(2)}</h1>`;
    } else if (line.startsWith('## ')) {
      html += `<h2 class="text-lg font-bold text-white mt-8 mb-3">${escapeHtml(line.slice(3))}</h2>`;
    } else if (line.startsWith('- **') && line.includes('**:')) {
      const colonIdx = line.indexOf('**:');
      const bold = escapeHtml(line.slice(3, colonIdx));
      const rest = escapeHtml(line.slice(colonIdx + 3));
      html += `<li class="ml-5 list-disc text-white/70"><strong>${bold}:</strong>${rest}</li>`;
      inList = true;
    } else if (line.startsWith('- ')) {
      if (!inList) { html += '<ul class="list-disc pl-5 space-y-2 my-3">'; inList = true; }
      html += `<li class="text-white/70">${escapeHtml(line.slice(2))}</li>`;
    } else if (line.trim() === '' && inList) {
      html += '</ul>';
      inList = false;
    } else if (line.startsWith('**') && line.endsWith('**')) {
      html += `<p class="text-sm text-white/70 leading-relaxed my-3"><strong>${escapeHtml(line.slice(2, -2))}</strong></p>`;
    } else if (line.trim()) {
      if (inList) { html += '</ul>'; inList = false; }
      const processed = escapeHtml(line)
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" class="text-indigo-400 hover:text-indigo-300 underline">$1</a>');
      html += `<p class="text-sm text-white/70 leading-relaxed my-3">${processed}</p>`;
    }
  }

  if (inList) html += '</ul>';
  return html;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function getContent(slug: string): string | null {
  const allowed = ['terms', 'privacy'];
  if (!allowed.includes(slug)) return null;

  const filePath = path.join(process.cwd(), 'public', 'legal', `${slug}.md`);
  try {
    return fs.readFileSync(filePath, 'utf-8');
  } catch {
    return null;
  }
}

export default async function LegalPage({ params }: LegalPageProps) {
  const { slug } = await params;
  const content = getContent(slug);
  const title = TITLES[slug] || slug;

  if (!content) {
    return (
      <div className="min-h-screen bg-[#060912] text-white p-6 md:p-12 max-w-4xl mx-auto">
        <h1 className="text-3xl font-black">Page not found</h1>
        <Link href="/signup" className="text-indigo-400 hover:text-indigo-300 underline mt-4 block">
          Back to sign up
        </Link>
      </div>
    );
  }

  const rendered = renderMarkdown(content);

  return (
    <div className="min-h-screen bg-[#060912] text-white p-6 md:p-12 max-w-4xl mx-auto">
      <Link
        href="/signup"
        className="inline-flex items-center gap-2 text-sm text-white/40 hover:text-white/60 transition-colors mb-8"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        Back
      </Link>

      <div
        className="[&_h1]:text-white [&_h2]:text-white [&_strong]:text-white/90 [&_a]:text-indigo-400 [&_p]:text-sm [&_p]:text-white/70 [&_p]:leading-relaxed [&_p]:my-3 [&_li]:text-white/70 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-2 [&_ul]:my-3"
        dangerouslySetInnerHTML={{ __html: rendered }}
      />
    </div>
  );
}
