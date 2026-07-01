import { motion, useScroll, useSpring } from 'framer-motion'
import Nav from './components/Nav'
import Hero from './components/Hero'
import Stats from './components/Stats'
import Services from './components/Services'
import Advantages from './components/Advantages'
import Products from './components/Products'
import Quality from './components/Quality'
import VideoSection from './components/VideoSection'
import Timeline from './components/Timeline'
import Exhibitions from './components/Exhibitions'
import Contact from './components/Contact'
import Footer from './components/Footer'

export default function App() {
  const { scrollYProgress } = useScroll()
  const scaleX = useSpring(scrollYProgress, { stiffness: 120, damping: 30, mass: 0.4 })

  return (
    <>
      <motion.div
        className="fixed inset-x-0 top-0 z-[70] h-[3px] origin-left"
        style={{ scaleX, background: 'linear-gradient(90deg, var(--color-gold-soft), var(--color-gold-deep))' }}
      />
      <Nav />
      <main>
        <Hero />
        <Stats />
        <Services />
        <Advantages />
        <Products />
        <Quality />
        <VideoSection />
        <Timeline />
        <Exhibitions />
        <Contact />
      </main>
      <Footer />
    </>
  )
}
