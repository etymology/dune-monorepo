function IO( modules )
{
  var winder = modules.get( "Winder" )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Load an I/O query into a table.
  // Input:
  //   listQuery - Query to run to get a list of I/O.
  //   itemQuery - Query to run to get status of a specific I/O point.
  //   tag - Tag to place I/O list after loading.
  //-----------------------------------------------------------------------------
  function loadIO_Set( listQuery, itemQuery, tag )
  {
    winder.remoteAction
    (
      listQuery,
      function( data )
      {
        var columnNames = [ "Name", "Value" ]
        var widths = [ "60%", "40%" ]
        var filteredTable = new FilteredTable( columnNames, false, widths )

        filteredTable.loadFromArray( data )
        filteredTable.display( tag )

        for ( var row in data )
        {
          var ioPoint = data[ row ]
          var name = ioPoint[ 0 ]

          var query = itemQuery.replace( "$", '"' + name + '"' )

          let localRow = row

          // Update function.
          winder.addPeriodicCallback
          (
            query,
            function( data )
            {
              // Get the cell id this data is stored.
              let id = filteredTable.getCellId( localRow, 1 )

              // If this cell exists...
              if ( id )
                $( "#" + id ).html( data )
            }
          )
        }
      }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Load all I/O.
  //-----------------------------------------------------------------------------
  function loadIO()
  {
    loadIO_Set( "LowLevelIO.getInputs()", "LowLevelIO.getInput( $ )", "#inputsDiv" )
    loadIO_Set( "LowLevelIO.getOutputs()", "LowLevelIO.getOutput( $ )", "#outputsDiv" )
    loadIO_Set( "LowLevelIO.getTags()", "LowLevelIO.getTag( $ )", "#tagsDiv" )
  }

  // Load I/O lists and have this function run after error recovery.
  loadIO()
  winder.addErrorClearCallback( loadIO )

  // //-----------------------------------------------------------------------------
  // // Uses:
  // //   Called when page loads.
  // //-----------------------------------------------------------------------------
  // $( document ).ready
  // (
  //   function()
  //   {
  //     // Load I/O lists and have this function run after error recovery.
  //     loadIO()
  //     winder.addErrorClearCallback( loadIO )
  //   }
  // )

  window[ "io" ] = this
}