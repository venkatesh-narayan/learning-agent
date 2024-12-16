export interface SuggestionsResponse {
    perplexity_response: string;
    moment?: {
        type: 'new_topic_no_context' | 'new_topic_with_context' | 'concept_struggle' | 'goal_direction';
        confidence: number;
        reasoning: string;
    };
    recommendations?: Array<{
        content_id: string;
        url: string;
        explanation: string;
        relevant_sections: string[];
    }>;
    line_analysis?: {
        inferred_goal: string;
        learning_progression: string;
        current_focus: string;
    };
    immediate: string[];
    broader: string[];
    deeper: string[];
}

export interface ApiResponse {
    recommendations: {
        perplexity_response: string;
        moment?: SuggestionsResponse['moment'];
        recommendations?: SuggestionsResponse['recommendations'];
        line_analysis?: SuggestionsResponse['line_analysis'];
    };
    suggestions: {
        immediate: string[];
        broader: string[];
        deeper: string[];
    };
}

export interface LearningMoment {
    type: 'new_topic_no_context' | 'new_topic_with_context' | 'concept_struggle' | 'goal_direction';
    confidence: number;
    reasoning: string;
}

export interface Recommendation {
    content_id: string;
    url: string;
    explanation: string;
    relevant_sections: string[];
}

export interface LineAnalysis {
    inferred_goal: string;
    learning_progression: string;
    current_focus: string;
}

export type ProcessStep = {
    id: string;
    label: string;
    description?: string;
};

export type ProcessStage =
    | 'initial'           // Getting Perplexity response
    | 'analyzing'         // Analyzing learning context
    | 'moment'            // Detecting learning moment
    | 'searching'         // Searching for content
    | 'extracting'        // Processing found content
    | 'recommendations'   // Generating final recommendations
    | 'failed'            // Failed to find useful content