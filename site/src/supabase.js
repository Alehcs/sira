import { createClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY;

// the publishable key only lets a player read questions and add their own bets, as the table rules allow
export const supabase = url && key ? createClient(url, key) : null;
