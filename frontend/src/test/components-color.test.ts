import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

describe('Contrôle de non-importation directe de couleur dans les composants', () => {
  function getComponentFiles(dir: string): string[] {
    const entries = fs.readdirSync(dir, { withFileTypes: true })
    const files: string[] = []

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name)
      if (entry.isDirectory()) {
        files.push(...getComponentFiles(fullPath))
      } else if (entry.isFile() && (entry.name.endsWith('.tsx') || entry.name.endsWith('.jsx'))) {
        if (!entry.name.includes('.test.') && !entry.name.includes('.spec.')) {
          files.push(fullPath)
        }
      }
    }
    return files
  }

  const srcDir = path.resolve(__dirname, '..')
  const componentDirs = ['components', 'pages', 'features', 'app'].map((d) => path.join(srcDir, d))

  const componentFiles = componentDirs.flatMap((d) =>
    fs.existsSync(d) ? getComponentFiles(d) : [],
  )

  it('trouve des fichiers composants à vérifier', () => {
    expect(componentFiles.length).toBeGreaterThan(0)
  })

  it("aucun composant n'importe de couleur directement depuis un module de tokens ou palette", () => {
    const colorImportRegex = /import\s+.*(?:color|palette|token).*from/i

    for (const file of componentFiles) {
      const content = fs.readFileSync(file, 'utf-8')
      const matches = content.match(colorImportRegex)
      expect(
        matches,
        `Le composant ${file} importe directement une couleur ou un jeton : ${matches?.[0]}`,
      ).toBeNull()
    }
  })

  it("aucun composant n'écrit de code hexadécimal en dur", () => {
    const hexColorRegex = /#[0-9a-fA-F]{3,8}/

    for (const file of componentFiles) {
      const content = fs.readFileSync(file, 'utf-8')
      const matches = content.match(hexColorRegex)
      expect(
        matches,
        `Le composant ${file} contient une couleur hexadécimale en dur : ${matches?.[0]}`,
      ).toBeNull()
    }
  })
})
