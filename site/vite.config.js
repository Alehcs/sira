import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// served from https://alehcs.github.io/sira/
export default defineConfig({ base: '/sira/', plugins: [react()] });
