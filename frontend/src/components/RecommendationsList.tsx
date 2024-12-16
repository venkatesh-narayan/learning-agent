import { useState } from 'react';
import { BookOpen, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import { Recommendation } from '@/lib/api';

interface RecommendationsListProps {
    recommendations: Recommendation[] | null;
    onInteraction: (contentId: string, type: string) => Promise<void>;
    isLoading?: boolean;
}

export function RecommendationsList({
    recommendations,
    onInteraction,
    isLoading
}: RecommendationsListProps) {
    const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({});

    const toggleItem = (contentId: string) => {
        setExpandedItems(prev => ({
            ...prev,
            [contentId]: !prev[contentId]
        }));
    };

    if (isLoading) {
        return (
            <div className="animate-pulse space-y-4">
                {[1, 2, 3].map(i => (
                    <div key={i} className="bg-gray-100 h-32 rounded-lg" />
                ))}
            </div>
        );
    }

    if (!recommendations?.length) {
        return (
            <div className="text-gray-500 text-center py-8">
                <BookOpen className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>No recommendations yet. Keep exploring topics to get personalized content suggestions!</p>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {recommendations.map((rec) => (
                <div
                    key={rec.content.url}
                    className="bg-white rounded-lg shadow border border-gray-200 overflow-hidden"
                >
                    <div className="p-4">
                        <div className="flex justify-between items-start">
                            <h3 className="font-semibold text-gray-900 mb-1">
                                {rec.content.title}
                            </h3>
                            <span className="text-sm text-gray-500 whitespace-nowrap ml-2">
                                {Math.round(rec.confidence * 100)}% match
                            </span>
                        </div>

                        <div className="flex gap-2 flex-wrap mt-2 mb-3">
                            {rec.content.topics.map((topic) => (
                                <span
                                    key={topic}
                                    className="px-2 py-1 bg-blue-50 text-blue-700 text-xs rounded-full"
                                >
                                    {topic}
                                </span>
                            ))}
                        </div>

                        <div className="space-y-2">
                            {rec.reasons.map((reason, idx) => (
                                <div
                                    key={idx}
                                    className="text-sm text-gray-600 flex items-start gap-2"
                                >
                                    <div className="min-w-[24px] pt-0.5">
                                        <div
                                            className="h-2 w-2 rounded-full bg-blue-500 mt-1.5"
                                            style={{
                                                opacity: 0.4 + (reason.confidence * 0.6)
                                            }}
                                        />
                                    </div>
                                    <p>{reason.explanation}</p>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="border-t border-gray-100">
                        <button
                            onClick={() => toggleItem(rec.content.url)}
                            className="w-full px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 flex items-center justify-between"
                        >
                            <span>
                                {expandedItems[rec.content.url] ? 'Show less' : 'Show more'}
                            </span>
                            {expandedItems[rec.content.url] ? (
                                <ChevronUp className="h-4 w-4" />
                            ) : (
                                <ChevronDown className="h-4 w-4" />
                            )}
                        </button>

                        {expandedItems[rec.content.url] && (
                            <div className="p-4 border-t border-gray-100 space-y-4">
                                {rec.content.sections.map((section, idx) => (
                                    <div key={idx}>
                                        <h4 className="font-medium text-gray-900 mb-1">
                                            {section.title}
                                        </h4>
                                        <p className="text-sm text-gray-600">
                                            {section.content.slice(0, 200)}
                                            {section.content.length > 200 && '...'}
                                        </p>
                                    </div>
                                ))}

                                <div className="pt-2">
                                    <a
                                        href={rec.content.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        onClick={() => onInteraction(rec.content.url, 'click')}
                                        className="inline-flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700"
                                    >
                                        Read full content
                                        <ExternalLink className="h-4 w-4" />
                                    </a>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
}