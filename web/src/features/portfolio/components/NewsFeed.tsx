'use client';

import { ExternalLink, Newspaper } from 'lucide-react';
import { useStockNews } from '../hooks/usePortfolio';

interface NewsFeedProps {
    symbol: string;
    limit?: number;
    title?: string;
}

export function NewsFeed({ symbol, limit = 10, title = 'Latest News' }: NewsFeedProps) {
    const { data, isLoading } = useStockNews(symbol, limit);

    if (isLoading) {
        return (
            <div className="glass-panel rounded-lg p-4 space-y-3">
                <h3 className="text-xs font-black uppercase tracking-widest text-white/40">{title}</h3>
                {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="animate-pulse space-y-1.5">
                        <div className="h-3 bg-white/10 rounded w-3/4" />
                        <div className="h-2 bg-white/5 rounded w-1/2" />
                    </div>
                ))}
            </div>
        );
    }

    if (!data?.articles || data.articles.length === 0) {
        return (
            <div className="glass-panel rounded-lg p-4">
                <div className="flex items-center gap-2 text-white/30">
                    <Newspaper className="h-4 w-4" />
                    <span className="text-xs">No recent news</span>
                </div>
            </div>
        );
    }

    return (
        <div className="glass-panel rounded-lg p-4 space-y-2">
            <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-black uppercase tracking-widest text-white/40">{title}</h3>
                <span className="text-[10px] text-white/20">{data.source}</span>
            </div>

            <div className="space-y-1 max-h-72 overflow-y-auto scrollbar-thin">
                {data.articles.map((article, i) => (
                    <a
                        key={article.uuid || i}
                        href={article.url || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block py-2 px-2 rounded-lg hover:bg-white/5 transition-colors group"
                    >
                        <div className="flex items-start justify-between gap-2">
                            <p className="text-sm text-white/80 group-hover:text-white transition-colors line-clamp-2">
                                {article.title}
                            </p>
                            <ExternalLink className="h-3 w-3 text-white/20 shrink-0 mt-1 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                            <span className="text-[10px] font-medium text-white/30">
                                {article.publisher}
                            </span>
                            {article.published_at && (
                                <>
                                    <span className="text-[10px] text-white/10">·</span>
                                    <span className="text-[10px] text-white/20">
                                        {new Date(article.published_at).toLocaleDateString()}
                                    </span>
                                </>
                            )}
                        </div>
                    </a>
                ))}
            </div>
        </div>
    );
}
