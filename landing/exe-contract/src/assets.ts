// Local optimized images live in /public/assets/img.
// Heavy media (63 MB video, animated GIFs) is streamed from the original
// CloudFront CDN to keep the repo and the deployment lean.
const IMG = '/assets/img'

export const img = {
  hero: `${IMG}/hero_6r_half.webp`,
  molecules: `${IMG}/abstract_molecules.webp`,
  labQuality: `${IMG}/lab_quality.webp`,
  gmpCorridor: `${IMG}/corridor_gmp_v1.webp`,
  buildingSign: `${IMG}/building_sign_on_red_panel.webp`,
  production1: `${IMG}/production1.webp`,
  production2: `${IMG}/production2.webp`,
  production3: `${IMG}/production3.webp`,
  production4: `${IMG}/production4.webp`,
}

export const exhibitionLogos: Record<string, string> = {
  AMWC: `${IMG}/amwc.webp`,
  IMCAS: `${IMG}/imcas.webp`,
  'Cosmoprof Bologna': `${IMG}/cosmoprof.webp`,
  'Cosmoprof Asia': `${IMG}/cosmoprof-asia-red.webp`,
  'Dubai Derma': `${IMG}/dubai-derma.webp`,
  'Beautyworld ME': `${IMG}/beautyworld-me.webp`,
  BeautyIstanbul: `${IMG}/beautyistanbul-logo-new.webp`,
  'in-cosmetics Asia': `${IMG}/in-cosmetics-asia.webp`,
}

const CDN = 'https://d2xsxph8kpxj0f.cloudfront.net/310419663028289097/PLqzh7o66gZyRQYpm9qXpX'
export const media = {
  productionVideo: `${CDN}/production-video-with-audio_c2f202b7.mp4`,
}

// Product category → representative image.
export const productImages = [img.molecules, img.labQuality, img.production2, img.production4]
