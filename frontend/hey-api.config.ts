import { createClient } from "@hey-api/openapi-ts";

createClient({
    input: "http://localhost:8000/openapi.json",
    output: "src/api",
    plugins: [
        {
            name: "@hey-api/client-axios",
            baseUrl: process.env.BASE_URL || "http://localhost:8000"
        }
    ]
})
