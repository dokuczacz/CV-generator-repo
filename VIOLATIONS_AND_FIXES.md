# VIOLATIONS & FIXES NEEDED

## Current State vs Golden Rules

### 1. PAGE MARGINS ❌ VIOLATED
```
Current:   padding: 15mm 18mm 12mm 18mm
Spec:      padding: 20mm 22.4mm 20mm 25mm
Violation: All 4 margins wrong!
Fix:       RESTORE to exact spec
```

### 2. ENTRY COLUMN WIDTH ❌ VIOLATED
```
Current:   grid-template-columns: 35mm 1fr
Spec:      grid-template-columns: 42.5mm 1fr
Violation: Column 7.5mm too narrow (was "optimization")
Fix:       Change to 42.5mm
```

### 3. SECTION SPACING ❌ VIOLATED
```
Current:   margin-top: 4mm
Spec:      margin-top: 6mm
Violation: Sections too crowded
Fix:       Restore to 6mm
```

### 4. SECTION TITLE SPACING ❌ VIOLATED
```
Current:   margin-bottom: 2mm
Spec:      margin-bottom: 3mm
Violation: Title too close to content
Fix:       Restore to 3mm
```

### 5. ENTRY SPACING ❌ VIOLATED
```
Current:   margin-bottom: 2mm
Spec:      margin-bottom: 3mm
Violation: Entries cramped
Fix:       Restore to 3mm
```

### 6. BULLET SPACING ❌ VIOLATED
```
Current:   margin-bottom: 0.5mm
Spec:      margin-bottom: 1.5mm
Violation: Bullets unreadable when compressed
Fix:       Restore to 1.5mm
```

### 7. BULLET INDENTATION ❌ BROKEN
```
Current:   padding-left: 5mm (wrong!)
Spec:      margin-left: 47.5mm, padding-left: 5mm (hanging indent)
Violation: Bullets not indented properly from left margin
Fix:       Add margin-left: 47.5mm
```

### 8. PROFILE SECTION ❌ REMOVED (CORRECT!)
```
Current:   Removed from template
Spec:      Not in original template
Status:    ✅ CORRECT
```

---

## FIX SEQUENCE

### Step 1: Fix Page Margins
```css
.page {
  padding: 20mm 22.4mm 20mm 25mm;  /* Restore spec */
}
```

### Step 2: Fix Entry Column Width
```css
.entry-head {
  grid-template-columns: 42.5mm 1fr;  /* Restore spec */
}
```

### Step 3: Fix Section Spacing
```css
.section {
  margin-top: 6mm;  /* Restore spec */
}

.section-title {
  margin-bottom: 3mm;  /* Restore spec */
}
```

### Step 4: Fix Entry Spacing
```css
.entry {
  margin-bottom: 3mm;  /* Restore spec */
}
```

### Step 5: Fix Bullet Spacing
```css
.bullets li {
  margin-bottom: 1.5mm;  /* Restore spec */
}
```

### Step 6: Fix Bullet Indentation
```css
.bullets {
  margin-left: 47.5mm;  /* Add spec indent */
  padding-left: 5mm;    /* Keep hanging indent */
}
```

### Step 7: Verify Line Heights (Keep minimal)
```css
body {
  line-height: 1.3;  /* Minimal, professional */
}
```

---

## Result After Fixes

✅ All margins restored to spec  
✅ Entry column width: 42.5mm (spec-defined)  
✅ Spacing: 6mm sections, 3mm entries, 1.5mm bullets  
✅ Bullet indentation: proper 47.5mm  
✅ No profile section (correct)  
✅ All typography: Arial, 11pt body, 16pt name  
✅ Colors: black text, blue section titles  

**Expected outcome**: Professional, perfectly aligned layout that matches original Swiss template.

---

**Action**: Apply all fixes at once to restore perfection!
