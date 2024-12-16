import { Brain, Search, FileSearch, Sparkles, Check, Loader2, MessageSquare } from 'lucide-react';

interface ProcessStep {
    id: string;
    label: string;
    description: string;
    icon: typeof Brain;
}

const PROCESS_STEPS: ProcessStep[] = [
    {
        id: 'initial',
        label: 'Getting Response',
        description: 'Getting Perplexity response...',
        icon: Search,
    },
    {
        id: 'analyzing',
        label: 'Analyzing Context',
        description: 'Analyzing your learning progression...',
        icon: Brain,
    },
    {
        id: 'searching',
        label: 'Finding Content',
        description: 'Searching for relevant content...',
        icon: FileSearch,
    },
    {
        id: 'recommendations',
        label: 'Generating Insights',
        description: 'Preparing personalized recommendations...',
        icon: Sparkles,
    },
    {
        id: 'suggestions',
        label: 'Generating Suggestions',
        description: 'Creating follow-up questions...',
        icon: MessageSquare,  // New icon for suggestions
    }
];

interface ProgressStepsProps {
    currentStep: string | null;
}

export function ProgressSteps({ currentStep }: ProgressStepsProps) {
    if (!currentStep) return null;

    const currentStepIndex = PROCESS_STEPS.findIndex(s => s.id === currentStep);

    return (
        <div className="w-full max-w-4xl mx-auto bg-white rounded-xl shadow-sm border border-gray-200 p-8">
            <div className="relative">
                {/* Progress line */}
                <div className="absolute left-0 top-6 w-full h-[2px] bg-gray-100" />
                <div
                    className="absolute left-0 top-6 h-[2px] bg-blue-500 transition-all duration-500"
                    style={{
                        width: `${((currentStepIndex + 1) / PROCESS_STEPS.length) * 100}%`
                    }}
                />

                {/* Steps */}
                <div className="relative flex justify-between items-start">
                    {PROCESS_STEPS.map((step, index) => {
                        const isActive = step.id === currentStep;
                        const isPast = currentStepIndex > index;
                        const Icon = step.icon;

                        return (
                            <div key={step.id} className="flex flex-col items-center w-32">
                                {/* Step circle */}
                                <div
                                    className={`
                                        w-12 h-12 rounded-full flex items-center justify-center 
                                        transition-all duration-300 relative
                                        ${isActive ? 'bg-blue-50 border-2 border-blue-500' : ''}
                                        ${isPast ? 'bg-green-50 border-2 border-green-500' : 'bg-white border-2 border-gray-200'}
                                    `}
                                >
                                    {isPast ? (
                                        <Check className="h-5 w-5 text-green-500" />
                                    ) : isActive ? (
                                        <>
                                            <Icon className="h-5 w-5 text-blue-500" />
                                            <span className="absolute -right-1 -bottom-1">
                                                <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
                                            </span>
                                        </>
                                    ) : (
                                        <Icon className="h-5 w-5 text-gray-400" />
                                    )}
                                </div>

                                {/* Label */}
                                <div className={`
                                    mt-3 text-center transition-all duration-300
                                    ${isActive ? 'text-blue-700' : 'text-gray-600'}
                                `}>
                                    <div className="font-medium text-sm">
                                        {step.label}
                                    </div>
                                    {isActive && (
                                        <div className="text-xs mt-1 text-gray-500">
                                            {step.description}
                                        </div>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}