import * as React from "react"

const TabsContext = React.createContext<{ value: string; onValueChange: (v: string) => void }>({ value: '', onValueChange: () => {} })

const Tabs = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & { value?: string, defaultValue?: string, onValueChange?: (v: string) => void }>(
  ({ className, value, defaultValue, onValueChange, ...props }, ref) => {
    const [tab, setTab] = React.useState(value || defaultValue || '')
    const handleValueChange = (v: string) => {
      setTab(v)
      if (onValueChange) onValueChange(v)
    }
    return (
      <TabsContext.Provider value={{ value: value !== undefined ? value : tab, onValueChange: handleValueChange }}>
        <div ref={ref} className={className} {...props} />
      </TabsContext.Provider>
    )
  }
)
Tabs.displayName = "Tabs"

const TabsList = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div ref={ref} className={`inline-flex h-9 items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground ${className || ''}`} {...props} />
))
TabsList.displayName = "TabsList"

const TabsTrigger = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & { value: string }>(
  ({ className, value, ...props }, ref) => {
    const context = React.useContext(TabsContext)
    const isSelected = context.value === value
    return (
      <button
        ref={ref}
        type="button"
        role="tab"
        aria-selected={isSelected}
        onClick={() => context.onValueChange(value)}
        className={`inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow ${isSelected ? 'bg-background text-foreground shadow' : ''} ${className || ''}`}
        {...props}
      />
    )
  }
)
TabsTrigger.displayName = "TabsTrigger"

const TabsContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & { value: string }>(
  ({ className, value, ...props }, ref) => {
    const context = React.useContext(TabsContext)
    if (context.value !== value) return null
    return (
      <div
        ref={ref}
        role="tabpanel"
        className={`mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${className || ''}`}
        {...props}
      />
    )
  }
)
TabsContent.displayName = "TabsContent"

export { Tabs, TabsList, TabsTrigger, TabsContent }
