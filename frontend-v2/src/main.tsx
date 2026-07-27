import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AppProviders } from './app/providers'
import { AppRoutes } from './app/router'
import './styles/globals.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode><AppProviders><BrowserRouter><AppRoutes /></BrowserRouter></AppProviders></StrictMode>,
)
