# Widget service (Ruby) -- intentionally smelly fixture for the generic pack.
class Widget
  STATUS = "pending-review"

  def initialize(name)
    @name = name
    @status = "pending-review" # TODO: derive from store
  end

  def promote
    # FIXME: validate transition
    @status = "pending-review"
  end

  def describe
    # HACK: hard-coded label
    "#{@name}: #{@status}"
  end
end
