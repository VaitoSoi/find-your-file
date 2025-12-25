import { Search } from "lucide-react";
import { Input } from "./ui/input";

export default function Header() {
    return <div className="w-full h-18 flex flex-row items-center rounded-md">
        <div className="text-2xl my-auto flex flex-row items-center gap-2 ml-5">
            <Search className="size-10" />
            <h1 className="font-[Be_Vietnam_Pro] font-semibold">Find your File</h1>
        </div>
        <div className="relative w-fit flex items-center m-auto">
            <Search className="absolute size-4 left-3.5 text-gray-400" />
            <Input
                placeholder="Search files..."
                className="p-5 pl-9 w-2xl rounded-2xl focus:border-none"
            // value={searchQuery}
            // onChange={(e) => setSearchQuery(e.target.value)}
            />
        </div>
    </div>;
}