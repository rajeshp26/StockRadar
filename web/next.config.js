const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'images.unsplash.com',
      },
    ],
  },

  turbopack: {
    root: path.resolve(__dirname), // Absolute path to the web directory itself
  },
  
  
};

module.exports = nextConfig;