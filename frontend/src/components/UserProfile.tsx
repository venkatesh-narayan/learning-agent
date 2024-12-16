import { LearningProfile, LearningPath } from '@/lib/api';
import { Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

interface UserProfileProps {
    profile: LearningProfile | null;
}

export function UserProfile({ profile }: UserProfileProps) {
    const [expandedPaths, setExpandedPaths] = useState<{ [key: string]: boolean }>({});

    if (!profile) {
        return (
            <div className="flex justify-center items-center p-8">
                <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
            </div>
        );
    }

    const togglePath = (pathId: string) => {
        setExpandedPaths(prev => ({
            ...prev,
            [pathId]: !prev[pathId]
        }));
    };

    const activePaths = [...profile.active_learning_paths].toReversed();

    if (activePaths.length === 0) {
        return (
            <div className="bg-white rounded-lg shadow border border-gray-200 p-4 text-gray-500 text-center">
                Start exploring topics to build your learning profile
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {activePaths.map((path, pathIdx) => {
                const pathId = `path-${pathIdx}`;
                const isExpanded = expandedPaths[pathId];
                const isCurrentFocus = pathIdx === 0;

                const hasDetails = (
                    path.knowledge_gaps.length > 0 ||
                    path.next_suggested_topics.length > 0
                );

                return (
                    <div
                        key={pathId}
                        className={`bg-white rounded-lg shadow border border-gray-200 ${isCurrentFocus ? 'border-blue-200' : ''}`}
                    >
                        <button
                            onClick={() => togglePath(pathId)}
                            className="w-full p-4 flex justify-between items-center text-left hover:bg-gray-50 transition-colors"
                        >
                            <div className="flex-1">
                                <h3 className="font-semibold text-gray-900 mb-1">
                                    {isCurrentFocus ? 'Current Focus' : 'Previous Focus'}
                                </h3>
                                <p className={`font-medium ${isCurrentFocus ? 'text-blue-600' : 'text-gray-600'}`}>
                                    {path.current_focus}
                                </p>

                                {/* Show a preview of what's inside */}
                                {!isExpanded && hasDetails && (
                                    <p className="text-sm text-gray-500 mt-1">
                                        {path.knowledge_gaps.length > 0 && `${path.knowledge_gaps.length} areas to review`}
                                        {path.knowledge_gaps.length > 0 && path.next_suggested_topics.length > 0 && ', '}
                                        {path.next_suggested_topics.length > 0 && `${path.next_suggested_topics.length} recommended topics`}
                                    </p>
                                )}
                            </div>
                            <div className="ml-2 flex items-center space-x-2">
                                {hasDetails && (
                                    <span className="text-sm text-gray-500 mr-2">
                                        {isExpanded ? 'Less' : 'More'}
                                    </span>
                                )}
                                {hasDetails && (
                                    isExpanded ? (
                                        <ChevronUp className="h-5 w-5 text-gray-400" />
                                    ) : (
                                        <ChevronDown className="h-5 w-5 text-gray-400" />
                                    )
                                )}
                            </div>
                        </button>

                        {isExpanded && hasDetails && (
                            <div className="px-4 pb-4 space-y-4 border-t border-gray-100">
                                {path.knowledge_gaps.length > 0 && (
                                    <div>
                                        <h4 className="font-medium text-gray-700 mb-2">Areas to Review</h4>
                                        <ul className="list-disc list-inside text-sm text-gray-900 space-y-1">
                                            {path.knowledge_gaps.map((gap, idx) => (
                                                <li key={idx} className="leading-relaxed">
                                                    {gap}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {path.next_suggested_topics.length > 0 && (
                                    <div>
                                        <h4 className="font-medium text-gray-700 mb-2">Recommended Topics</h4>
                                        <ul className="list-disc list-inside text-sm text-gray-900 space-y-1">
                                            {path.next_suggested_topics.map((topic, idx) => (
                                                <li key={idx} className="leading-relaxed">
                                                    {topic}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}