import { Suggestions } from '@/lib/api';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

interface SuggestionsListProps {
    suggestions: Suggestions | null;
    onSelect: (suggestion: string) => void;
    isDisabled: boolean;
}

export function SuggestionsList({ suggestions, onSelect, isDisabled }: SuggestionsListProps) {
    const [expanded, setExpanded] = useState({
        broader: false,
        deeper: false,
    });

    if (!suggestions) {
        return (
            <div className="text-gray-500 text-center py-4">
                Ask a question to see suggestions
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Immediate Suggestions */}
            {suggestions.immediate.length > 0 && (
                <div className="bg-white rounded-lg shadow border border-gray-200">
                    <div className="p-4">
                        <h3 className="font-semibold text-gray-900">Next Steps</h3>
                        <p className="text-sm text-gray-500">Direct follow-up questions</p>
                    </div>
                    <ul className="divide-y divide-gray-100">
                        {suggestions.immediate.map((suggestion, idx) => (
                            <li
                                key={idx}
                                onClick={() => !isDisabled && onSelect(suggestion)}
                                className={`p-3 text-gray-900 ${!isDisabled ? 'hover:bg-blue-50 cursor-pointer' : 'opacity-50'} transition-colors`}
                            >
                                {suggestion}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Broader Context */}
            {suggestions.broader.length > 0 && (
                <div className="bg-white rounded-lg shadow border border-gray-200">
                    <button
                        onClick={() => setExpanded(prev => ({ ...prev, broader: !prev.broader }))}
                        className="w-full p-4 flex justify-between items-center"
                        disabled={isDisabled}
                    >
                        <div>
                            <h3 className="font-semibold text-gray-900">Broader Context</h3>
                            <p className="text-sm text-gray-500">Related aspects to consider</p>
                        </div>
                        {expanded.broader ? (
                            <ChevronUp className="h-5 w-5 text-gray-400" />
                        ) : (
                            <ChevronDown className="h-5 w-5 text-gray-400" />
                        )}
                    </button>
                    {expanded.broader && (
                        <ul className="divide-y divide-gray-100">
                            {suggestions.broader.map((suggestion, idx) => (
                                <li
                                    key={idx}
                                    onClick={() => !isDisabled && onSelect(suggestion)}
                                    className={`p-3 text-gray-900 ${!isDisabled ? 'hover:bg-blue-50 cursor-pointer' : 'opacity-50'} transition-colors`}
                                >
                                    {suggestion}
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}

            {/* Deeper Understanding */}
            {suggestions.deeper.length > 0 && (
                <div className="bg-white rounded-lg shadow border border-gray-200">
                    <button
                        onClick={() => setExpanded(prev => ({ ...prev, deeper: !prev.deeper }))}
                        className="w-full p-4 flex justify-between items-center"
                        disabled={isDisabled}
                    >
                        <div>
                            <h3 className="font-semibold text-gray-900">Deeper Understanding</h3>
                            <p className="text-sm text-gray-500">Explore underlying concepts</p>
                        </div>
                        {expanded.deeper ? (
                            <ChevronUp className="h-5 w-5 text-gray-400" />
                        ) : (
                            <ChevronDown className="h-5 w-5 text-gray-400" />
                        )}
                    </button>
                    {expanded.deeper && (
                        <ul className="divide-y divide-gray-100">
                            {suggestions.deeper.map((suggestion, idx) => (
                                <li
                                    key={idx}
                                    onClick={() => !isDisabled && onSelect(suggestion)}
                                    className={`p-3 text-gray-900 ${!isDisabled ? 'hover:bg-blue-50 cursor-pointer' : 'opacity-50'} transition-colors`}
                                >
                                    {suggestion}
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </div>
    );
}