# AstroGraph Frontend

AstroGraph interactive 3D and 2D celestial codebase intelligence interface built with React, Vite, Three.js, Cytoscape.js, and Firebase Authentication.

---

## Quick Start (For Anyone Cloning From GitHub)

1. **Install Dependencies**:
   ```bash
   cd frontend
   npm install
   ```

2. **Start Dev Server**:
   ```bash
   npm run dev
   ```
   Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Authentication & Google Sign-In

### Out-of-the-Box Google Login
The project includes default Firebase client configuration (`src/firebase.js`), so anyone who clones the repository from GitHub can immediately click **"Continue with Google"** and sign in without any initial setup or `.env` files required.

### Important Note on Localhost vs 127.0.0.1
Firebase Authentication security requires requests to originate from an **Authorized Domain**.
- `localhost` is authorized by default.
- If you open the site via `http://localhost:5173`, Google Sign-In works immediately.
- The app automatically normalizes requests from `127.0.0.1` to `localhost` to prevent `auth/unauthorized-domain` errors.
- If deploying to a custom domain (e.g., Vercel, Netlify, Render), add your domain in **Firebase Console → Authentication → Settings → Authorized domains**.

### Guest / Demo Mode
You can also click **"Explore as Guest"** on the landing page to access the full dashboard and graph visualizers instantly without signing in.

---

## Custom Environment Variables (Optional)

If you wish to connect your own Firebase project or custom backend:
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Update the `VITE_FIREBASE_*` credentials with your own Firebase Web App configuration from the Firebase Console.
3. Restart the dev server (`npm run dev`).
