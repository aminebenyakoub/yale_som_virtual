import { useCallback, useEffect, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import World from './World.jsx'
import Player from './Player.jsx'
import Minimap from './Minimap.jsx'
import TouchControls from './TouchControls.jsx'
import ChatPanel from './ChatPanel.jsx'
import { EYE, SPAWN } from './layout.js'

export default function App() {
  const [locked, setLocked] = useState(false)
  const [where, setWhere] = useState('')
  const [showMap, setShowMap] = useState(true)
  const lockRef = useRef()
  const mapRef = useRef()
  const onLock = useCallback((v) => setLocked(v), [])
  const onWhere = useCallback((w) => setWhere(w), [])
  // phones have no pointer lock, so they get a joystick + drag-to-look instead
  const [isTouch] = useState(() => matchMedia('(pointer: coarse)').matches) // phones + tablets; touchscreen laptops still get mouse mode
  const [touchOn, setTouchOn] = useState(false)
  const touchRef = useRef({ active: false, move: [0, 0], look: [0, 0], jump: false })
  const setTouch = (on) => {
    touchRef.current.active = on
    touchRef.current.move = [0, 0]
    setTouchOn(on)
  }
  const playing = locked || touchOn

  // AI professors: walk up to one and press E (or tap Talk) to chat
  const talkRef = useRef({ near: false, open: false, speaking: false })
  const [nearProf, setNearProf] = useState(null)
  const [chatProf, setChatProf] = useState(null)
  const wasTouch = useRef(false)
  const onNearProfessor = useCallback((p) => setNearProf(p), [])
  const openChat = useCallback(() => {
    if (!nearProf) return
    wasTouch.current = touchRef.current.active
    if (wasTouch.current) setTouch(false)
    document.exitPointerLock?.()
    talkRef.current.open = true
    setChatProf(nearProf)
  }, [nearProf]) // eslint-disable-line react-hooks/exhaustive-deps
  const closeChat = useCallback(() => {
    talkRef.current.open = false
    setChatProf(null)
    if (wasTouch.current) setTouch(true)
    else lockRef.current?.() // straight back to walking (needs the click; after Esc the overlay shows instead)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const k = (e) => {
      if (e.target.closest?.('input, textarea')) return
      if (e.code === 'KeyM') setShowMap((v) => !v)
      if (e.code === 'KeyE' && playing && !chatProf) openChat()
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [playing, chatProf, openChat])

  return (
    <>
      <Canvas
        camera={{ fov: 72, near: 0.05, far: 800, position: [SPAWN.x, EYE, SPAWN.z] }}
        dpr={[1, 1.75]}
      >
        <World talkRef={talkRef} onNearProfessor={onNearProfessor} />
        <Player lockRef={lockRef} mapRef={mapRef} touchRef={touchRef} onLock={onLock} onWhere={onWhere} />
      </Canvas>

      <div className="where">
        <span className="dot" />
        {where}
      </div>
      <div className={showMap ? 'mapwrap' : 'mapwrap hidden'}>
        <Minimap drawRef={mapRef} />
      </div>
      <button className="maptoggle" onClick={() => setShowMap((s) => !s)}>
        {showMap ? 'hide map' : 'map'}
      </button>
      {playing && <div className="crosshair" />}
      {touchOn && <TouchControls touchRef={touchRef} onPause={() => setTouch(false)} />}

      {nearProf && playing && !chatProf && (
        <div className="talkhint">
          {touchOn ? (
            <button className="go" onClick={openChat}>
              Talk to Prof. {nearProf.name.split(' ').slice(-1)[0]}
            </button>
          ) : (
            <>
              Press <kbd>E</kbd> to talk to Prof. {nearProf.name.split(' ').slice(-1)[0]}
            </>
          )}
        </div>
      )}
      {chatProf && <ChatPanel prof={chatProf} talkRef={talkRef} onClose={closeChat} />}

      {!playing && !chatProf && (
        <div className="overlay" onClick={() => (isTouch ? setTouch(true) : lockRef.current?.())}>
          <div className="card">
            <div className="kicker">Yale SOM · Evans Hall</div>
            <h1>Floor 2</h1>
            <p className="sub">Classroom drums, the cloister, Ross Library, the Beinecke Terrace Room, and the courtyard.</p>
            <button className="go">{isTouch ? 'Tap to walk in' : 'Click to walk in'}</button>
            {!isTouch && (
              <button
                className="go alt"
                onClick={(e) => {
                  e.stopPropagation()
                  setTouch(true)
                }}
              >
                Use on-screen joystick
              </button>
            )}
            {isTouch ? (
              <div className="keys">
                <span><b>Left thumb</b> joystick to walk (push all the way to hurry)</span>
                <span><b>Right thumb</b> drag to look</span>
              </div>
            ) : (
              <div className="keys">
                <span><b>W A S D</b> walk</span>
                <span><b>Mouse</b> look</span>
                <span><b>Shift</b> sprint</span>
                <span><b>Space</b> jump</span>
                <span><b>C</b> crouch</span>
                <span><b>M</b> map</span>
                <span><b>Esc</b> pause</span>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
