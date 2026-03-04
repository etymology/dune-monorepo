///////////////////////////////////////////////////////////////////////////////
// Name: FilterTable.js
// Uses: Table that has filtered columns and is sortable.
// Date: 2016-05-11
// Author(s):
//   Andrew Que <aque@bb7.com>
// Notes:
//   Uses ECMAScript 6 functions.  Will not function on all mobile devices.
//   $$$FUTURE - Fix this fact and remove use of 'let'?
///////////////////////////////////////////////////////////////////////////////

//=============================================================================
// Uses:
//   A filterable, sortable table display class.
// Inputs:
//   columnNames - Array of column names.
//   columnFilterEnables - Either:
//     An array of booleans as to which columns should allow filters (true),
//     and which should not (false).
//     True/false to enable/disable filters on all columns.
//   columnWidth - An array of width parameters for each column.  Optional.
//=============================================================================
function FilteredTable( columnNames, columnFilterEnables, columnWidths )
{
  var self = this

  // A unique id for this object.
  this.id = Math.floor( Math.random() * 0xFFFFFFFF )

  // Table data.
  var data

  // Used to filter data.  List where each entry contains an array with the
  // column to be filtered, and a list of true/false values for each possible
  // value of the cell.
  // Example:
  // [ # Column         Enable for all possible column values.
  //   [ "firstName", { "Jane" : true, "Joe" : false, "John" : true } ],
  //   [ "lastName",  { "Smith" : true, "Doe" : false } ],
  // ]
  // This would filter the data to include first names of Jane and John who also
  // have the last name Smith.
  var columnFilters = null

  // Used to sort columns.  Double list.  Each entry contains an array with the
  // column to be sorted, and the direction (-1/1) of sort.
  var sortArray = []

  // A filtered/sorted copy of 'data'.
  var filteredData

  // Callback to run after display is complete.
  var displayCallback = null

  // Lookup table between the raw array and the filtered.
  // Used to translate the row index of 'data' to the row id in the HTML table.
  var sortLookup = {}

  // Callback function when a row is clicked.
  var rowCallback

  // If using a global filter enable, or no filters are enabled...
  if ( ( false === columnFilterEnables )
    || ( true === columnFilterEnables )
    || ( undefined === columnFilterEnables ) )
  {
    // Assume they don't want filtering options (sorting only).
    var defaultSetting = false

    // If all columns are to allow filtering...
    if ( columnFilterEnables )
      defaultSetting = true

    // Build filter enables with default value.
    columnFilterEnables = []
    for ( var index in columnNames )
    {
      var column = columnNames[ index ]
      columnFilterEnables.push( defaultSetting )
    }
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Get a list of all the unique items from a column.
  //---------------------------------------------------------------------------
  this.getUnique = function( column )
  {
    var results = []
    for ( var rowIndex in data )
    {
      var row = data[ rowIndex ]
      var item = row[ column ]
      if ( results.indexOf( item ) == -1 )
        results.push( item )
    }

    return results
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Filter the data displayed.
  // Inputs:
  //   column - Index of the column to filter.  Optional.
  //   filter - Data to allow in column.  Optional.
  // Note:
  //   If column and filter are omitted, the last filter is used.  Useful to
  //   recompute displayed data.
  //   This only sets the filter--must call display to show results.
  //---------------------------------------------------------------------------
  this.filter = function( column, filter )
  {
    filteredData = []

    // Loop through all the raw data looking for matches...
    for ( var rowIndex in data )
    {
      var row = data[ rowIndex ].slice()
      row.push( rowIndex )

      var addRow = true
      for ( var column in row )
        // If this row is a match, add it to the filter data.
        if ( ( null != columnFilters )
          && ( null != columnFilters[ column ] ) )
        {
          addRow &= columnFilters[ column ][ row[ column ] ]
        }

      if ( addRow )
        filteredData.push( row )
    }

    for ( var forwardIndex in sortArray )
    {
      // Sort happens in reverse order using the oldest filters first, and
      // moving to the newest last.
      var index = sortArray.length - 1 - forwardIndex
      var sortColumn    = sortArray[ index ][ 0 ]
      var sortDirection = sortArray[ index ][ 1 ]

      // If sorting is enabled...
      if ( ( null !== sortColumn )
        && ( null !== sortDirection ) )
      {
        // Do a sort using a custom callback that sorts based on the select column
        // and direction of sort.
        filteredData.sort
        (
          function( a, b )
          {
            var result
            if ( ( $.isNumeric( a[ sortColumn ] ) )
              && ( $.isNumeric( b[ sortColumn ] ) ) )
            {
              a = parseFloat( a[ sortColumn ] )
              b = parseFloat( b[ sortColumn ] )
              result = 0
              if ( a > b )
                result = 1
              else
                result = -1
            }
            else
            {
              // Get the objects in the selected column as strings.
              a = a[ sortColumn ].toString()
              b = b[ sortColumn ].toString()

              // Compare strings.
              result = a.localeCompare( b )

            }

            // Account for sort direction.
            // (Remember: sort direction is either 1 or -1.)
            result *= sortDirection

            return result
          }
        )
      }
    }
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Set the sorting order.
  // Input:
  //   column - Which column to sort by.
  //   direction - True for low to high, false for high to low.
  // Note:
  //   This only sets the sort--must call display to show sorted results.
  //---------------------------------------------------------------------------
  this.setSort = function( column, direction )
  {
    if ( direction )
      direction = 1
    else
      direction = -1

    // If this sort is already being applied, remove it.
    for ( index in sortArray )
    {
      if ( column == sortArray[ index ][ 0 ]  )
        sortArray.splice( index, 1 )
    }

    // Push new sort ordering to the front of the array.
    sortArray.unshift( [ column, direction ] )

    // Re-run the filter.
    self.filter()
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Display the filtered data.
  // Inputs:
  //   tableId - Id of the table tag to place data.  Tag will be overwritten.
  //---------------------------------------------------------------------------
  var temp = 0
  this.display = function( tableId )
  {
    // Tag id without hash character.
    var idString = tableId.replace( "#", "" )

    var displayDiv =
      $( "<div />" )
        .attr( "class", "filter-table" )
        .attr( "id", idString )

    // Create a new table element to replace old.
    var table = $( "<table />" )
      .appendTo( displayDiv )

    function setupColumnWidths( table, columnWidths )
    {
      // If there are column widths to use...
      if ( columnWidths )
      {
        // For each of the columns, set the width.
        // NOTE: Additional styles can be applied from style sheet--this is only
        // for widths.
        var tableRow = $( "<colgroup />" ).appendTo( table )
        for ( var index in columnWidths )
        {
          var width = columnWidths[ index ]
          $( "<col/>" )
            .appendTo( tableRow )
            .width( width )
        }
      }
    }

    setupColumnWidths( table, columnWidths )

    var newColumnFilters = []
    var tableHeader = $( "<thead />" ).appendTo( table )

    // Table heading with column names.
    var tableRow = $( "<tr />" ).appendTo( tableHeader )
    for ( let columnIndex in columnNames )
    {
      // Look up column name.
      var columnName = columnNames[ columnIndex ]

      // Alias the column index for callback function.
      let localColumn = columnIndex

      var cell = $( "<th/>" )
        .appendTo( tableRow )
        .css( "position", "relative" )
        .click
        (
          function()
          {
            var message = $( "<p />" ).attr( "id", idString ).text( "Sorting..." )
            $( tableId ).replaceWith( message )

            if ( ( ! sortArray[ 0 ] )
              || ( localColumn != sortArray[ 0 ][ 0 ] ) )
            {
              self.setSort( localColumn, 1 )
            }
            else
              sortArray[ 0 ][ 1 ] *= -1

            self.filter()
            self.display( tableId )
          }
        )

      var subCell = $( "<span/>" ).text( columnName )
      newColumnFilters[ columnIndex ] = null
      if ( columnFilterEnables[ columnIndex ] )
      {
        let localMouseControl = false
        var dropDown =
          $( "<div>" )
            .attr( "class", "dropDown" )
            .mouseout
            (
              function()
              {
                localMouseControl = false
              }
            )
            .mouseenter
            (
              function()
              {
                localMouseControl = true
              }
            )
            .click
            (
              function()
              {
                return localMouseControl
              }
            )
            .append
            (
              $( "<p>" ).html( columnName + "&#9662;" )
            )

        subCell = dropDown

        let optionsDiv = $( "<div/>" )
          .appendTo( dropDown )
          .mouseleave
          (
            function()
            {
              self.filter()
              self.display( tableId )
            }
          )

        // Select all options.
        $( "<button />" )
          .appendTo( optionsDiv )
          .text( "All" )
          .click
          (
            function()
            {
              $( optionsDiv )
                .find( "button.toggle" )
                .each
                (
                  function()
                  {
                    $( this ).click()
                  }
                )
            }
          )

        // Select no options.
        $( "<button />" )
          .appendTo( optionsDiv )
          .text( "None" )
          .click
          (
            function()
            {
              $( optionsDiv )
                .find( "button.toggleDown" )
                .each
                (
                  function()
                  {
                    $( this ).click()
                  }
                )
            }
          )

        newColumnFilters[ columnIndex ] = {}

        // Get all the unique items in this column.
        var items = this.getUnique( columnIndex )
        items.sort()

        // Display filtering options for column.
        for ( var index in items )
        {
          let item = items[ index ]
          newColumnFilters[ columnIndex ][ item ] = true

          var buttonValue = true
          var buttonClass = "toggleDown"
          if ( null != columnFilters )
          {
            buttonValue = columnFilters[ columnIndex ][ item ]
            if ( ! buttonValue )
              buttonClass = "toggle"
          }

          $( "<button />" )
            .appendTo( optionsDiv )
            .val( buttonValue )
            .attr( "class", buttonClass )
            .text( item )
            .click
            (
              function()
              {
                $( this ).toggleClass( "toggle" )
                $( this ).toggleClass( "toggleDown" )

                var value = false
                if ( $( this ).attr( 'class' ) == "toggleDown" )
                  value = true

                columnFilters[ localColumn ][ item ] = value

                $( this ).val( value )
              }
            )
        }

        columnFilters = newColumnFilters
      }

      cell.append( subCell )

      // If this is the sorted column, draw the arrow.
      if ( ( sortArray[ 0 ] )
        && ( columnIndex == sortArray[ 0 ][ 0 ] ) )
      {
        var arrow = "&#8593;"
        if ( -1 == sortArray[ 0 ][ 1 ] )
          arrow = "&#8595;"

        // Create a <div> tag to hold sorting arrow.
        var labelId = "columnSort_" + this.id + "_" + columnIndex
        $( "<div/>" )
          .attr( "id", labelId )
          .css
          (
            {
              "border" : "none",
              "background" : "none",
              "position" : "absolute",
              "right" : 4,
              "top" : 0,
              "margin" : 0,
              "padding" : 0
            }
          )
          .html( arrow )
          .appendTo( cell )

      }
    }

    // If there is as yet no filtered data, use the full data set.
    if ( ! filteredData )
      this.filter()

    var outerDiv =
      $( "<div />" )
        .attr( "class", "filter-table-outer" )
        .appendTo( displayDiv )

    var innerDiv =
      $( "<div />" )
        .attr( "class", "filter-table-inner" )
        .appendTo( outerDiv )

    // Create a new table element to replace old.
    var table = $( "<table />" )
      .appendTo( innerDiv )

    setupColumnWidths( table, columnWidths )

    // Reset sort lookup table.  We'll rebuild it during this loop.
    sortLookup = {}

    // Fill the body of the table with data.
    var tableBody = $( "<tbody />" ).appendTo( table )
    for ( let row in filteredData )
    {
      var rowData = filteredData[ row ]

      // Last column is the sort index.
      var indexColumn = rowData.length - 1
      let lookupValue = rowData[ indexColumn ]
      sortLookup[ lookupValue ] = row

      var tableRow = $( "<tr />" )
        .attr( "id", "row_" + this.id + "_" + row )
        .appendTo( tableBody )

      // If there is a callback for rows, register it.
      if ( rowCallback )
        tableRow.click
        (
          function()
          {
            rowCallback( lookupValue )
          }
        )

      for ( var index in rowData )
      {
        var item = rowData[ index ]
        if ( index != indexColumn )
          $( "<td/>" )
            .appendTo( tableRow )
            .attr( "id", "cell_" + this.id + "_" + row + "_" + index )
            .text( item )
      }
    }

    $( tableId ).replaceWith( displayDiv )

    if ( displayCallback )
      displayCallback()
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Load table data from an array.
  // Input:
  //   newData - 2d array with all data for the table.
  //   columnMapping - Translation table to map which column of the input data
  //     go to which columns of the table.  Optional.
  // Example:
  //   var columnNames = [ 'Name', 'Birth', 'Weight', 'SSN' ]
  //   var columnMapping = [ 0, 2, 1 ]
  //   var data =
  //     [
  //       [ 'Bob', '1/1/1970', 150, 123-45-6789 ],
  //       [ 'Jane','2/2/1972', 120, 123-45-5429 ],
  //       [ 'Jim', '3/3/1973', 170, 123-45-6234 ]
  //     ]
  //   var filteredTable = new FilteredTable( columnNames )
  //   filteredTable.loadFromArray( data, columnMapping )
  //
  //   In the example, the SSN column is not displayed in the table, and weight
  //   is displayed before birth.
  //---------------------------------------------------------------------------
  this.loadFromArray = function( newData, columnMapping )
  {
    data = []

    // If no column mapping is given, assume a 1:1 correlation between the new
    // data and the resulting data.
    if ( ! columnMapping )
    {
      columnMapping = []
      for ( var index in columnNames )
        columnMapping.push( index )
    }

    // Loop through all rows in new data...
    for ( var rowIndex in newData )
    {
      var row = newData[ rowIndex ]
      // Build a row using column mapping.
      // Allows columns to be out-of-order or ignored all together.
      var rowData = []
      for ( var mappingIndex in columnMapping )
      {
        var itemIndex = columnMapping[ mappingIndex ]
        var item = row[ itemIndex ]

        rowData.push( item )
      }

      data.push( rowData )
    }

    this.filter()
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Get the cell id for a given row and column.
  // Input:
  //   row - Desired row.
  //   column - Desired column.
  // Output:
  //   Tag id for desired cell.  null if this row doesn't exist (i.e. has been
  //   filtered out).
  //---------------------------------------------------------------------------
  this.getCellId = function( row, column )
  {
    var result = null
    if ( row in sortLookup )
    {
      row = sortLookup[ row ]
      result = "cell_" + this.id + "_" + row + "_" + column
    }

    return result
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Set a callback to run after display.
  // Input:
  //   callback - Callback function.
  //---------------------------------------------------------------------------
  this.setDisplayCallback = function( callback )
  {
    displayCallback = callback
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Set a callback to when a row is clicked.
  // Input:
  //   callback - Callback function.
  // Notes:
  //   Doesn't take effect until 'display' is called.
  //---------------------------------------------------------------------------
  this.setRowCallback = function( callback )
  {
    rowCallback = callback
  }

}
