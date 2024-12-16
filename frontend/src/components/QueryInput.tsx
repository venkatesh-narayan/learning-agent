import { Search, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface QueryInputProps {
    value: string;
    onChange: (value: string) => void;
    onSubmit: (query: string) => void;
    isLoading: boolean;
}

export function QueryInput({ value, onChange, onSubmit, isLoading }: QueryInputProps) {
    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        console.log('Form submitted with value:', value); // Debug log
        const trimmedValue = value.trim();
        if (trimmedValue && !isLoading) {
            onSubmit(trimmedValue);
        }
    };

    return (
        <div className="w-full max-w-3xl mx-auto">
            <form onSubmit={handleSubmit} className="relative flex items-center">
                <Input
                    type="text"
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder="What would you like to learn about?"
                    className="pr-24"
                />
                <div className="absolute right-1 top-1 bottom-1">
                    <Button
                        type="submit"
                        disabled={!value.trim() || isLoading}
                        variant="default"
                        size="sm"
                        className="h-full"
                        onClick={() => console.log('Button clicked')} // Debug log
                    >
                        {isLoading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <>
                                <Search className="h-4 w-4 mr-2" />
                                Ask
                            </>
                        )}
                    </Button>
                </div>
            </form>
        </div>
    );
}