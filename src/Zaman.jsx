import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import Labubu, { YALE_BLUE } from './Labubu.jsx'

// Prof. Tauhid Zaman, by his own declaration: hoodie, Labubus, says "yo", Bangladeshi, dark skin.
// Face from his faculty photo: round face, very short buzzed hair, light stubble, no glasses.
// Built like Professor.jsx: primitives, figure faces +z, 1 unit = 1 m.
// talkRef.current = { near, open, speaking } is shared with the chat UI: he turns to face the
// camera when you are close or talking to him, and his mouth moves while he speaks.

const SKIN = '#7a4a2a'
const HAIR = '#16110e'
const HOODIE = YALE_BLUE
const NEAR = 4.5 // meters: close enough to talk
const LOOK = 9 // meters: close enough that he notices you

const mats = new Map()
const m = (color, o = {}) => {
  const k = color + JSON.stringify(o)
  if (!mats.has(k)) mats.set(k, new THREE.MeshStandardMaterial({ color, roughness: 0.85, ...o }))
  return mats.get(k)
}
const SPH = new THREE.SphereGeometry(1, 24, 16)
const CAP_TOP = new THREE.SphereGeometry(1, 24, 12, 0, Math.PI * 2, 0, Math.PI * 0.42) // buzz cut
const JAW = new THREE.SphereGeometry(1, 24, 12, 0, Math.PI * 2, Math.PI * 0.56, Math.PI * 0.44) // stubble
const CYL = new THREE.CylinderGeometry(1, 1, 1, 20)
const BOX = new THREE.BoxGeometry(1, 1, 1)
const CAP = new THREE.CapsuleGeometry(1, 1, 6, 12)
const TORUS = new THREE.TorusGeometry(1, 0.35, 10, 24)

const B = ({ g = SPH, c, p, s, r = [0, 0, 0], o }) => <mesh geometry={g} material={m(c, o)} position={p} scale={s} rotation={r} />

function chestTex() {
  const c = document.createElement('canvas')
  c.width = 256
  c.height = 128
  const g = c.getContext('2d')
  g.font = 'bold 92px system-ui, sans-serif'
  g.textAlign = 'center'
  g.fillStyle = '#ffffff'
  g.fillText('yo', 128, 96)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a))

export default function Zaman({ position = [0, 0, 0], rotation = 0, talkRef, onNear }) {
  const root = useRef()
  const head = useRef()
  const mouth = useRef()
  const armR = useRef()
  const armL = useRef()
  const wasNear = useRef(false)
  const chest = useMemo(() => new THREE.MeshBasicMaterial({ map: chestTex(), transparent: true }), [])
  const tmp = useMemo(() => new THREE.Vector3(), [])

  useFrame(({ clock, camera }, rawDt) => {
    const dt = Math.min(rawDt, 0.05)
    const t = clock.elapsedTime
    const talk = talkRef.current
    const dx = camera.position.x - position[0]
    const dz = camera.position.z - position[2]
    const dist = Math.hypot(dx, dz)

    const near = dist < NEAR
    if (near !== wasNear.current) {
      wasNear.current = near
      talk.near = near
      onNear?.(near)
    }

    // body: face you when you are around, otherwise scan the lecture hall
    const facing = talk.open || dist < LOOK
    const want = facing ? Math.atan2(dx, dz) : rotation + Math.sin(t * 0.4) * 0.35
    const r = root.current
    r.rotation.y += wrap(want - r.rotation.y) * Math.min(1, dt * (facing ? 5 : 2))

    // head: whatever yaw the body hasn't caught up with yet, plus pitch up/down to your eyes
    head.current.rotation.order = 'YXZ' // turn, then nod
    head.current.getWorldPosition(tmp)
    const yawLeft = facing ? wrap(want - r.rotation.y) : 0
    const pitch = facing ? Math.atan2(camera.position.y - (tmp.y + 0.1), Math.max(dist, 0.3)) : -0.05
    head.current.rotation.y += (THREE.MathUtils.clamp(yawLeft, -0.9, 0.9) - head.current.rotation.y) * Math.min(1, dt * 8)
    head.current.rotation.x += (THREE.MathUtils.clamp(-pitch, -0.5, 0.5) - head.current.rotation.x) * Math.min(1, dt * 8)

    // talking: mouth flaps and the right hand gestures; idle: slow breathing sway
    const speaking = talk.speaking
    mouth.current.scale.y = speaking ? 0.012 + Math.abs(Math.sin(t * 13) * Math.sin(t * 5.3)) * 0.03 : 0.012
    armR.current.rotation.x = speaking ? -0.7 + Math.sin(t * 4) * 0.35 : -0.15 + Math.sin(t * 1.2) * 0.04
    armR.current.rotation.z = speaking ? -0.35 + Math.sin(t * 2.6) * 0.15 : -0.12
    armL.current.rotation.x = -0.9 + Math.sin(t * 1.3) * 0.05 // holding the Labubu up
  })

  return (
    <group ref={root} position={position} rotation={[0, rotation, 0]}>
      {/* sneakers */}
      {[-1, 1].map((sx) => (
        <group key={sx}>
          <B g={BOX} c="#f4f4f4" p={[0.1 * sx, 0.05, 0.04]} s={[0.11, 0.1, 0.27]} />
          <B g={BOX} c="#ff4fa3" p={[0.1 * sx, 0.015, 0.04]} s={[0.115, 0.03, 0.275]} />
        </group>
      ))}
      {/* jeans */}
      {[-1, 1].map((sx) => (
        <B key={sx} g={CYL} c="#2c3e5c" p={[0.1 * sx, 0.5, 0]} s={[0.075, 0.82, 0.08]} />
      ))}
      <B g={CYL} c="#2c3e5c" p={[0, 0.9, 0]} s={[0.19, 0.12, 0.13]} />

      {/* hoodie: body, ribbed hem, kangaroo pocket, "yo" on the chest, hood bunched behind the neck */}
      <mesh geometry={CAP} material={m(HOODIE)} position={[0, 1.2, 0]} scale={[0.22, 0.2, 0.15]} />
      <B g={CYL} c="#002a55" p={[0, 0.94, 0]} s={[0.215, 0.06, 0.148]} />
      <B g={BOX} c="#002a55" p={[0, 1.03, 0.14]} s={[0.24, 0.12, 0.02]} />
      <mesh material={chest} position={[0, 1.24, 0.153]}>
        <planeGeometry args={[0.24, 0.12]} />
      </mesh>
      <B g={TORUS} c={HOODIE} p={[0, 1.47, -0.06]} r={[Math.PI / 2 - 0.3, 0, 0]} s={[0.13, 0.11, 0.13]} />
      {[-1, 1].map((sx) => (
        <group key={sx}>
          <B g={CYL} c="#f4f4f4" p={[0.05 * sx, 1.405, 0.15]} s={[0.006, 0.1, 0.006]} />
          <B g={CYL} c="#f4f4f4" p={[0.05 * sx, 1.35, 0.152]} s={[0.01, 0.022, 0.01]} />
        </group>
      ))}
      {/* Labubu keychain on the hoodie pocket */}
      <Labubu height={0.12} fur="#c78bd6" expression="happy" position={[0.13, 0.93, 0.16]} />

      {/* right arm: gestures while he talks */}
      <group ref={armR} position={[-0.25, 1.43, 0]}>
        <mesh geometry={CAP} material={m(HOODIE)} position={[0, -0.24, 0]} scale={[0.065, 0.2, 0.065]} />
        <B g={CYL} c="#002a55" p={[0, -0.47, 0]} s={[0.06, 0.04, 0.06]} />
        <B c={SKIN} p={[0, -0.53, 0.01]} s={[0.045, 0.055, 0.04]} />
      </group>
      {/* left arm: holds up his Labubu */}
      <group ref={armL} position={[0.25, 1.43, 0]} rotation={[0, 0, 0.1]}>
        <mesh geometry={CAP} material={m(HOODIE)} position={[0, -0.24, 0]} scale={[0.065, 0.2, 0.065]} />
        <B g={CYL} c="#002a55" p={[0, -0.47, 0]} s={[0.06, 0.04, 0.06]} />
        <B c={SKIN} p={[0, -0.53, 0.01]} s={[0.045, 0.055, 0.04]} />
        <group position={[0, -0.6, 0.02]} rotation={[0.9, 0, 0]}>
          <Labubu height={0.3} fur="#ff8fc8" expression="mischief" shirt="yale" />
        </group>
      </group>

      {/* neck + head (head pivots at the neck so it can look at you) */}
      <B g={CYL} c={SKIN} p={[0, 1.5, 0]} s={[0.055, 0.08, 0.055]} />
      <group ref={head} position={[0, 1.55, 0]}>
        <B c={SKIN} p={[0, 0.12, 0]} s={[0.122, 0.138, 0.13]} />
        {[-1, 1].map((sx) => (
          <B key={sx} c={SKIN} p={[0.124 * sx, 0.12, -0.005]} s={[0.022, 0.036, 0.022]} />
        ))}
        {/* buzz cut, hairline set back a little */}
        <mesh geometry={CAP_TOP} material={m(HAIR)} position={[0, 0.125, -0.012]} rotation={[-0.32, 0, 0]} scale={[0.126, 0.142, 0.134]} />
        {/* stubble: a thin dark shell on the jaw */}
        <mesh
          geometry={JAW}
          material={m('#2a1a10', { transparent: true, opacity: 0.45 })}
          position={[0, 0.12, 0.003]}
          scale={[0.125, 0.141, 0.133]}
        />
        {/* eyes, brows, nose */}
        {[-1, 1].map((sx) => (
          <group key={sx}>
            <B c="#ffffff" p={[0.044 * sx, 0.15, 0.112]} s={[0.022, 0.016, 0.012]} />
            <B c="#1a0f0a" p={[0.044 * sx, 0.15, 0.122]} s={[0.012, 0.012, 0.008]} />
            <B g={BOX} c={HAIR} p={[0.046 * sx, 0.183, 0.117]} r={[0, 0, -0.12 * sx]} s={[0.05, 0.013, 0.012]} />
          </group>
        ))}
        <B c="#6b3f22" p={[0, 0.112, 0.128]} s={[0.02, 0.025, 0.02]} />
        {/* big easy grin; the inner mouth opens while he talks */}
        <B g={BOX} c="#ffffff" p={[0, 0.068, 0.127]} s={[0.07, 0.018, 0.01]} />
        <mesh ref={mouth} geometry={BOX} material={m('#3a1410')} position={[0, 0.056, 0.126]} scale={[0.06, 0.012, 0.01]} />
      </group>
    </group>
  )
}
