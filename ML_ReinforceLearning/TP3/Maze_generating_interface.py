#!/usr/bin/env python
# coding: utf-8




import numpy
import tkinter



#class dealing with the cells
class Cell():
   
    #define the filling colours 
    FILLED_COLOR_BG = "blue"
    EMPTY_COLOR_BG = "white"
    FILLED_COLOR_BORDER = "blue"
    EMPTY_COLOR_BORDER = "black"

    def __init__(self, master, x, y, size, fill=False):
        #Constructor of the object called by Cell(...)
        self.master = master
        self.abs = x #coordinates
        self.ord = y
        self.size = size
        self.fill = fill

    def _switch(self):
        #Switch if the cell is filled or not
        self.fill= not self.fill

    def draw(self):
        #order to the cell to draw its representation on the canvas
        if self.master != None:
            fill = Cell.FILLED_COLOR_BG
            outline = Cell.FILLED_COLOR_BORDER

            if not self.fill:
                fill = Cell.EMPTY_COLOR_BG
                outline = Cell.EMPTY_COLOR_BORDER

            xmin = self.abs * self.size
            xmax = xmin + self.size
            ymin = self.ord * self.size
            ymax = ymin + self.size

            self.master.create_rectangle(xmin, ymin, xmax, ymax, fill=fill,
                                         outline=outline)


class CellGridCanvas(tkinter.Canvas):
    #constructor of canvas
    def __init__(self, master, rows_cnt, columns_cnt, cell_size,
                 *args, **kwargs):

        kwargs["width"] = cell_size * columns_cnt
        kwargs["height"] = cell_size * rows_cnt
        tkinter.Canvas.__init__(self, master, *args, **kwargs)

        self.rows_cnt = rows_cnt
        self.columns_cnt = columns_cnt

        self.cell_size = cell_size

        self.grid = []
        for row in range(rows_cnt):
            line = []
            for column in range(columns_cnt):
                line.append(Cell(self, column, row, cell_size))

            self.grid.append(line)

        # Memorize the cells that have been modified to avoid many switching of
        # state during mouse motion.
        self.switched = []

        #bind click action
        self.bind("<Button-1>", self.handleMouseClick)
        #bind moving while clicking
        self.bind("<B1-Motion>", self.handleMouseMotion)
        #bind release button action - clear the memory of midified cells.
        self.bind("<ButtonRelease-1>", lambda event: self.switched.clear())

        self.draw()

    def draw(self):
        for row in self.grid:
            for cell in row:
                cell.draw()

    def _eventCoords(self, event):
        row = int(event.y / self.cell_size)
        column = int(event.x / self.cell_size)
        return row, column

    def handleMouseClick(self, event):
        row, column = self._eventCoords(event)
        cell = self.grid[row][column]
        cell._switch()
        cell.draw()
        #add the cell to the list of cell switched during the click
        self.switched.append(cell)

    def handleMouseMotion(self, event):
        row, column = self._eventCoords(event)
        try:
            cell = self.grid[row][column]
        except IndexError:
            return

        if cell not in self.switched:
            cell._switch()
            cell.draw()
            self.switched.append(cell)

    def clear(self):
        for row in self.grid:
            for cell in row:
                cell.fill = False
        self.draw()

    def to_array(self):
        array = numpy.zeros((self.rows_cnt, self.columns_cnt))
        for i, row in enumerate(self.grid):
            for j, cell in enumerate(row):
                if cell.fill:
                    array[i, j] = 1
        return array


class CellGrid(tkinter.Frame):
    """Adapter class to be able to recreate a grid canvas at will."""

    # Default cell size in pixels
    CELL_SIZE = 20

    def __init__(self, *args, **kwargs):
        tkinter.Frame.__init__(self, *args, **kwargs)
        self.grid_canvas = None

    def draw(self, rows_cnt, columns_cnt, cell_size=None):
        """Redraw the grid canvas with the given dimensions."""
        # Destory old grid canvas
        if self.grid_canvas:
            self.grid_canvas.destroy()

        # Draw the new grid canvas
        cell_size = cell_size or CellGrid.CELL_SIZE
        self.grid_canvas = CellGridCanvas(self, rows_cnt, columns_cnt,
                                          cell_size)
        self.grid_canvas.pack()

    def clear(self):
        self.grid_canvas.clear()

    def to_array(self):
        return self.grid_canvas.to_array()


class App(tkinter.Tk):

    # Pixel size for horizontal margin
    HMARGIN = 10

    DEFAULT_ROWS = 10
    DEFAULT_COLUMNS = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title("Get out of the maze!")

        # Dimensions frame to set dimensions
        frame = tkinter.Frame(self)
        frame.pack(padx=self.HMARGIN)
        lbl = tkinter.Label(frame, text="Set the maze dimensions:")
        lbl.grid(row=0, pady=5)
        lbl = tkinter.Label(frame, text="Rows")
        lbl.grid(row=1, column=0, sticky=tkinter.W)
        self.rows_entry = tkinter.Entry(frame)
        self.rows_entry.insert(tkinter.END, str(self.DEFAULT_ROWS))
        self.rows_entry.grid(row=1, column=1)
        lbl = tkinter.Label(frame, text="Columns", anchor="w")
        lbl.grid(row=2, column=0, sticky=tkinter.W)
        self.columns_entry = tkinter.Entry(frame)
        self.columns_entry.insert(tkinter.END, str(self.DEFAULT_COLUMNS))
        self.columns_entry.grid(row=2, column=1)

        # Grid: create it before packing it, to pass it to button's callback.
        self.grid = CellGrid(self)

        # Refresh button, to refetch the dimensions and redraw the maze
        btn = tkinter.Button(self, text="Refresh dimensions",
                             command=self.onRefresh)
        btn.pack(pady=5)

        # Grid label
        text = "Draw the path in the maze by holding the mouse over the grid, there should be only 1 exit"
        lbl = tkinter.Label(self, text=text)
        lbl.pack(padx=self.HMARGIN)

        # Add grid
        self.grid.draw(self.DEFAULT_ROWS, self.DEFAULT_COLUMNS)
        self.grid.pack(padx=self.HMARGIN, pady=10)

        # Buttons frame to use as a placeholder to place buttons side-by-side
        btn_frame = tkinter.Frame(self)
        btn_frame.pack(pady=10)

        # Run button
        btn = tkinter.Button(btn_frame, text="Create Matrix", command=self.onSave)
        btn.pack(side=tkinter.RIGHT)

        # Clear button
        btn = tkinter.Button(btn_frame, text="Clear", command=self.onClear)
        btn.pack(side=tkinter.RIGHT, padx=5)

        
    def onSave(self):
        self.A = self.grid.to_array()
        # Close the window
        self.destroy()

    def onClear(self):
        self.grid.clear()

    def onRefresh(self):
        # Fetch dimensions
        try:
            rows = int(self.rows_entry.get())
        except ValueError:
            # FIXME: Show a pop-up window to validate input
            pass

        try:
            columns = int(self.columns_entry.get())
        except ValueError:
            # FIXME: Show a pop-up window to validate input
            pass
    
        # Draw new grid
        self.grid.draw(rows, columns)


