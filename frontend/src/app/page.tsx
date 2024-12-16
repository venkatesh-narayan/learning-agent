'use client';

import { useState, useRef } from 'react';
import { Search, ChevronRight } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { QueryInput } from '@/components/QueryInput';
import { ProgressSteps } from '@/components/ProgressSteps';
import { type SuggestionsResponse } from '@/lib/types';
import Markdown from 'react-markdown';

const TEST_USER_ID = 'test_user_1';

const MOMENT_MESSAGES = {
    'new_topic_no_context': "It looks like this is a new topic that you don't have any background in. Here are some great supplementary materials to help you get started:",
    'new_topic_with_context': "You have some relevant background that will help here. Here are some materials that build on what you already know:",
    'concept_struggle': "Let's try looking at this from a different angle. Here are some alternative explanations that might help:",
    'goal_direction': "Here's a structured approach to help organize your learning in this area:"
} as const;

export default function Home() {
    const [query, setQuery] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [response, setResponse] = useState<SuggestionsResponse | null>(null);
    const [currentStep, setCurrentStep] = useState<string | null>(null);
    const [isSelecting, setIsSelecting] = useState(false);
    const lastValidStepRef = useRef<string | null>(null);  // Keep track of last valid step


    console.log('Rendering with query:', query); // Debug log

    const handleQuerySubmit = async (queryText: string) => {
        console.log('handleQuerySubmit called with:', queryText);
        try {
            setLoading(true);
            setError(null);
            setResponse(null);
            setCurrentStep('initial');

            // Create WebSocket connection
            const ws = new WebSocket(`ws://localhost:8000/ws/query?user_id=${TEST_USER_ID}&query=${encodeURIComponent(queryText)}`);

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('Received websocket message:', data);

                if (data.type === 'complete') {
                    setResponse({
                        perplexity_response: data.data.recommendations.perplexity_response,
                        moment: data.data.recommendations.moment,
                        recommendations: data.data.recommendations.recommendations,
                        line_analysis: data.data.recommendations.line_analysis,
                        immediate: data.data.suggestions.immediate || [],
                        broader: data.data.suggestions.broader || [],
                        deeper: data.data.suggestions.deeper || [],
                    });
                } else if (data.step && data.step !== lastValidStepRef.current) {
                    lastValidStepRef.current = data.step;
                    setCurrentStep(data.step);
                } else {
                    // If we get a message without a step, maintain the last known step
                    setCurrentStep(lastValidStepRef.current);
                }
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                setError('Connection error');
            };

            ws.onclose = () => {
                setLoading(false);
                lastValidStepRef.current = null;
                setCurrentStep(null);
            };

        } catch (err) {
            console.error('Error:', err);
            setError(err instanceof Error ? err.message : 'An error occurred');
            setLoading(false);
        }
    };

    const handleSuggestionSelect = async (suggestion: string) => {
        setIsSelecting(true);
        setQuery(suggestion);
        try {
            await handleQuerySubmit(suggestion);
        } catch (e) {
            setError('Failed to process suggestion');
            console.error(e);
        } finally {
            setIsSelecting(false);
        }
    };

    return (
        <main className="min-h-screen bg-gray-50">
            {/* Header */}
            <div className="border-b bg-white">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="py-6">
                        <h1 className="text-2xl font-semibold text-black">Learning Agent</h1>
                    </div>
                </div>
            </div>

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
                {/* Search */}
                <div className="max-w-3xl mx-auto">
                    <QueryInput
                        value={query}
                        onChange={setQuery}
                        onSubmit={handleQuerySubmit}
                        isLoading={loading}
                    />
                    {error && (
                        <p className="mt-2 text-sm text-red-600">{error}</p>
                    )}
                </div>

                {/* Progress Steps */}
                {currentStep && (
                    <div className="mb-8">
                        <ProgressSteps currentStep={currentStep} />
                    </div>
                )}

                {response && (
                    <div className="space-y-8">
                        {/* Perplexity Response - Full Width */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-black">Response</CardTitle>
                            </CardHeader>
                            <CardContent className="prose prose-black max-w-none">
                                <Markdown>{response.perplexity_response}</Markdown>
                            </CardContent>
                        </Card>

                        {/* Learning Context - If Available */}
                        {(response.moment || response.line_analysis) && (
                            <div className="bg-blue-50 rounded-lg p-6 space-y-4">
                                {response.moment && (
                                    <p className="text-black font-medium">
                                        {MOMENT_MESSAGES[response.moment]}
                                    </p>
                                )}
                                {response.line_analysis && (
                                    <p className="text-black">
                                        <span className="font-medium">Goal:</span> {response.line_analysis.inferred_goal}
                                    </p>
                                )}
                            </div>
                        )}

                        {/* Two Column Layout */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                            {/* Left Column - Query Suggestions */}
                            <div>
                                <Card>
                                    <CardHeader>
                                        <CardTitle className="text-black">Related Questions</CardTitle>
                                    </CardHeader>
                                    <CardContent className="h-[500px] overflow-y-auto">
                                        {/* Next Steps */}
                                        <div className="mb-6">
                                            <h3 className="text-sm font-medium text-black mb-3">Next Steps</h3>
                                            <div className="space-y-2">
                                                {response.immediate.map((question, idx) => (
                                                    <button
                                                        key={idx}
                                                        onClick={() => handleSuggestionSelect(question)}
                                                        className="w-full text-left px-4 py-2 rounded-lg border bg-white hover:bg-gray-50 text-black text-sm"
                                                        disabled={loading}
                                                    >
                                                        {question}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>

                                        {/* Broader Context */}
                                        <div className="mb-6">
                                            <h3 className="text-sm font-medium text-black mb-3">Broader Context</h3>
                                            <div className="space-y-2">
                                                {response.broader.map((question, idx) => (
                                                    <button
                                                        key={idx}
                                                        onClick={() => handleSuggestionSelect(question)}
                                                        className="w-full text-left px-4 py-2 rounded-lg border bg-white hover:bg-gray-50 text-black text-sm"
                                                        disabled={loading}
                                                    >
                                                        {question}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>

                                        {/* Deeper Understanding */}
                                        <div>
                                            <h3 className="text-sm font-medium text-black mb-3">Deeper Understanding</h3>
                                            <div className="space-y-2">
                                                {response.deeper.map((question, idx) => (
                                                    <button
                                                        key={idx}
                                                        onClick={() => handleSuggestionSelect(question)}
                                                        className="w-full text-left px-4 py-2 rounded-lg border bg-white hover:bg-gray-50 text-black text-sm"
                                                        disabled={loading}
                                                    >
                                                        {question}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            </div>

                            {/* Right Column - Recommendations and Knowledge State */}
                            <div className="space-y-8">
                                {/* Recommendations */}
                                {response.recommendations && response.recommendations.length > 0 && (
                                    <Card>
                                        <CardHeader>
                                            <CardTitle className="text-black">Recommended Content</CardTitle>
                                        </CardHeader>
                                        <CardContent className="h-[300px] overflow-y-auto">
                                            <div className="space-y-4">
                                                {response.recommendations.map((rec) => (
                                                    <div key={rec.content_id} className="group border rounded-lg p-4 hover:border-blue-200 transition-colors">
                                                        <h3 className="font-medium text-black">
                                                            {new URL(rec.url).hostname.replace('www.', '')}
                                                        </h3>
                                                        <p className="mt-2 text-sm text-black">{rec.explanation}</p>
                                                        {rec.relevant_sections.length > 0 && (
                                                            <div className="mt-3 space-y-2">
                                                                {rec.relevant_sections.map((section, idx) => (
                                                                    <p key={idx} className="text-sm text-black pl-3 border-l-2 border-gray-200">
                                                                        {section}
                                                                    </p>
                                                                ))}
                                                            </div>
                                                        )}
                                                        <a
                                                            href={rec.url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="mt-4 inline-flex items-center text-sm text-blue-600 hover:text-blue-800"
                                                        >
                                                            Read Article <ChevronRight className="ml-1 w-4 w-4" />
                                                        </a>
                                                    </div>
                                                ))}
                                            </div>
                                        </CardContent>
                                    </Card>
                                )}

                                {/* Knowledge State */}
                                {response.line_analysis && (
                                    <Card>
                                        <CardHeader>
                                            <CardTitle className="text-black">Knowledge State</CardTitle>
                                        </CardHeader>
                                        <CardContent>
                                            <div className="space-y-6">
                                                <div>
                                                    <h3 className="text-sm font-medium text-black mb-2">Current Focus</h3>
                                                    <p className="text-black">{response.line_analysis.current_focus}</p>
                                                </div>
                                                <div>
                                                    <h3 className="text-sm font-medium text-black mb-2">Progress</h3>
                                                    <p className="text-black">{response.line_analysis.learning_progression}</p>
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </main>
    );
}
