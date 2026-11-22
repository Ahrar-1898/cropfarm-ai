# CropFarmAI Dashboard

## Run on this computer

Use Node.js 26.13.0 and npm 11.20.0 (the root `.nvmrc` selects the Node.js version). From the repository root, install the locked frontend dependencies and start Vite:

```bash
nvm install
nvm use
npm ci --prefix frontend
npm --prefix frontend run dev
```

Open `http://localhost:5173`.

## Open on Windows or a phone on the same Wi-Fi

Start the network-accessible development server on the computer hosting the project:

```bash
npm --prefix frontend run dev:network
```

Find that computer's private IPv4 address:

- Windows: run `ipconfig` and look for the active adapter's **IPv4 Address**.
- macOS: run `ipconfig getifaddr en0` (or check System Settings → Wi-Fi → Details).
- Linux: run `hostname -I`.

On the Windows computer or phone, open `http://<host-ip>:5173`. For example, on this development network: `http://192.168.29.141:5173`.

Both devices must be on the same trusted Wi-Fi/LAN. If prompted, allow Node/Vite through the host computer's firewall on **Private networks only**. Do not expose the development server to the public internet. Press `Ctrl+C` in the host terminal to stop it.

The network command serves this React dashboard preview; authentication, Supabase data, Groq chat, and crop-model inference are not connected in this frontend yet.
